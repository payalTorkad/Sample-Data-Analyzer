import io
import json
import math
import re
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Smart Data Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- Styling -----------------------------------------
st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1500px;}
    [data-testid="stMetric"] {background: linear-gradient(135deg, rgba(99,102,241,.10), rgba(14,165,233,.08));
        border: 1px solid rgba(120,130,160,.20); padding: 14px 16px; border-radius: 14px;}
    .hero {padding: 1.25rem 1.5rem; border-radius: 18px;
        background: linear-gradient(115deg, rgba(79,70,229,.18), rgba(14,165,233,.12));
        border: 1px solid rgba(120,130,160,.25); margin-bottom: 1.2rem;}
    .hero h1 {margin: 0 0 .35rem 0;}
    .muted {color: #8490a5;}
    div[data-testid="stTabs"] button {font-weight: 600;}
</style>
""", unsafe_allow_html=True)

# ----------------------------- Helpers ----------------------------------------
def read_uploaded_file(uploaded):
    name = uploaded.name.lower()
    raw = uploaded.getvalue()
    if name.endswith(".csv"):
        # Try common encodings and delimiters; fall back to pandas default.
        for encoding in ("utf-8-sig", "utf-8", "latin1"):
            try:
                return pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python")
            except Exception:
                pass
        return pd.read_csv(io.BytesIO(raw))
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))
    if name.endswith(".json"):
        return pd.read_json(io.BytesIO(raw))
    raise ValueError("Unsupported file. Upload CSV, XLSX, XLS, or JSON.")

def normalize_column_names(df):
    out = df.copy()
    new_names = []
    for i, col in enumerate(out.columns):
        name = str(col).strip()
        name = re.sub(r"\s+", "_", name)
        name = re.sub(r"[^\w\-]", "", name)
        new_names.append(name or f"column_{i+1}")
    # Make duplicate names unique
    counts = {}
    unique = []
    for name in new_names:
        counts[name] = counts.get(name, 0) + 1
        unique.append(name if counts[name] == 1 else f"{name}_{counts[name]}")
    out.columns = unique
    return out

def clean_data(df, numeric_strategy, categorical_strategy, remove_exact_duplicates,
              trim_strings, standardize_categories, drop_empty_rows):
    """Conservative, repeatable cleaning. Returns cleaned data + action log."""
    out = df.copy()
    log = []
    before_rows, before_cols = out.shape

    # Normalize headers
    old_columns = list(out.columns)
    out = normalize_column_names(out)
    if list(out.columns) != old_columns:
        log.append(f"Standardized column names ({len(out.columns)} columns).")

    # Trim whitespace in text cells
    if trim_strings:
        text_cols = out.select_dtypes(include=["object", "string"]).columns
        changed = 0
        for col in text_cols:
            s = out[col]
            trimmed = s.map(lambda x: x.strip() if isinstance(x, str) else x)
            changed += int((s.astype("string") != trimmed.astype("string")).sum())
            out[col] = trimmed
        if changed:
            log.append(f"Trimmed leading/trailing whitespace in {changed:,} text cells.")

    # Convert blank strings to missing values
    text_cols = out.select_dtypes(include=["object", "string"]).columns
    blanks = 0
    for col in text_cols:
        mask = out[col].map(lambda x: isinstance(x, str) and x.strip() == "")
        blanks += int(mask.sum())
        out.loc[mask, col] = np.nan
    if blanks:
        log.append(f"Converted {blanks:,} blank text cells to missing values.")

    # Infer numeric strings where conversion is overwhelmingly successful.
    converted = []
    for col in out.select_dtypes(include=["object", "string"]).columns:
        nonnull = out[col].dropna()
        if len(nonnull) >= 3:
            candidate = nonnull.astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("₹", "", regex=False)
            parsed = pd.to_numeric(candidate, errors="coerce")
            if parsed.notna().mean() >= 0.95:
                out[col] = pd.to_numeric(out[col].astype("string").str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("₹", "", regex=False), errors="coerce")
                converted.append(col)
    if converted:
        log.append("Converted numeric-like columns: " + ", ".join(converted[:10]) + ("…" if len(converted) > 10 else "."))

    # Optional category normalization: casefold and collapse whitespace.
    if standardize_categories:
        cat_cols = out.select_dtypes(include=["object", "string", "category"]).columns
        changed = 0
        for col in cat_cols:
            s = out[col]
            normalized = s.map(lambda x: re.sub(r"\s+", " ", x.strip()).title() if isinstance(x, str) else x)
            changed += int((s.astype("string") != normalized.astype("string")).sum())
            out[col] = normalized
        if changed:
            log.append(f"Standardized capitalization/spacing in {changed:,} text cells.")

    # Remove fully empty rows.
    if drop_empty_rows:
        old = len(out)
        out = out.dropna(how="all")
        removed = old - len(out)
        if removed:
            log.append(f"Removed {removed:,} completely empty rows.")

    # Remove exact duplicates.
    if remove_exact_duplicates:
        old = len(out)
        out = out.drop_duplicates()
        removed = old - len(out)
        if removed:
            log.append(f"Removed {removed:,} exact duplicate rows.")

    # Fill missing values, column by column.
    filled = 0
    for col in out.columns:
        missing = int(out[col].isna().sum())
        if missing == 0:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            if numeric_strategy == "Median":
                fill_value = out[col].median()
            elif numeric_strategy == "Mean":
                fill_value = out[col].mean()
            elif numeric_strategy == "Zero":
                fill_value = 0
            else:
                continue
            if pd.notna(fill_value):
                out[col] = out[col].fillna(fill_value)
                filled += missing
                log.append(f"Filled {missing:,} missing value(s) in '{col}' with numeric {numeric_strategy.lower()} ({fill_value:g}).")
        else:
            if categorical_strategy == "Most frequent":
                modes = out[col].mode(dropna=True)
                if not modes.empty:
                    out[col] = out[col].fillna(modes.iloc[0])
                    filled += missing
                    log.append(f"Filled {missing:,} missing value(s) in '{col}' with most frequent value.")
            elif categorical_strategy == "Unknown":
                out[col] = out[col].fillna("Unknown")
                filled += missing
                log.append(f"Filled {missing:,} missing value(s) in '{col}' with 'Unknown'.")
            # Leave missing: no change

    if not log:
        log.append("No cleaning changes were needed.")
    return out, log, (before_rows, before_cols)

def quality_score(df):
    if df.empty or df.shape[1] == 0:
        return 0.0
    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 0.0
    missing_rate = df.isna().sum().sum() / total_cells
    duplicate_rate = df.duplicated().mean() if len(df) > 1 else 0
    score = max(0, 100 * (1 - 0.7 * missing_rate - 0.3 * duplicate_rate))
    return round(score, 1)

def make_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def make_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cleaned Data")
    return buffer.getvalue()

def format_num(value):
    if pd.isna(value):
        return "—"
    if isinstance(value, (int, np.integer)):
        return f"{value:,}"
    if isinstance(value, (float, np.floating)):
        return f"{value:,.2f}"
    return str(value)

# ----------------------------- Sidebar ----------------------------------------
with st.sidebar:
    st.markdown("## 📊 Smart Data Analyzer")
    st.caption("Upload → clean → analyze → export")
    st.divider()
    uploaded = st.file_uploader(
        "Upload your dataset",
        type=["csv", "xlsx", "xls", "json"],
        help="Supported formats: CSV, Excel, and JSON.",
    )
    st.markdown("### Cleaning settings")
    numeric_strategy = st.selectbox("Missing numeric values", ["Median", "Mean", "Zero", "Leave missing"], index=0)
    categorical_strategy = st.selectbox("Missing text values", ["Most frequent", "Unknown", "Leave missing"], index=0)
    remove_duplicates = st.checkbox("Remove exact duplicate rows", value=True)
    trim_strings = st.checkbox("Trim extra spaces", value=True)
    standardize_categories = st.checkbox("Standardize text capitalization", value=False)
    drop_empty_rows = st.checkbox("Remove completely empty rows", value=True)
    run_cleaning = st.button("✨ Clean and analyze", type="primary", use_container_width=True)
    st.caption("Your file is processed in this Streamlit session. Avoid uploading confidential data to a public deployment.")

# ----------------------------- Main -------------------------------------------
st.markdown("""
<div class="hero">
  <h1>Smart Data Analyzer</h1>
  <div class="muted">Turn raw CSV, Excel, or JSON files into clean data and actionable insights — automatically.</div>
</div>
""", unsafe_allow_html=True)

if uploaded is None:
    st.info("👈 Upload a dataset from the sidebar to begin.")
    st.markdown("### What you can do")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**🧹 Clean data**\n\nRemove exact duplicates, handle missing values, trim spaces, and normalize text.")
    c2.markdown("**🔎 Explore data**\n\nView data types, missing values, summary statistics, correlations, and outliers.")
    c3.markdown("**📥 Export results**\n\nDownload cleaned CSV/Excel files and a cleaning log.")
    st.stop()

try:
    raw_df = read_uploaded_file(uploaded)
except Exception as exc:
    st.error(f"Could not read this file: {exc}")
    st.stop()

if raw_df.empty:
    st.warning("This file has no rows to analyze.")
    st.stop()

if run_cleaning or "cleaned_df" not in st.session_state or st.session_state.get("uploaded_name") != uploaded.name:
    cleaned_df, cleaning_log, original_shape = clean_data(
        raw_df, numeric_strategy, categorical_strategy, remove_duplicates,
        trim_strings, standardize_categories, drop_empty_rows
    )
    st.session_state.cleaned_df = cleaned_df
    st.session_state.cleaning_log = cleaning_log
    st.session_state.original_shape = original_shape
    st.session_state.uploaded_name = uploaded.name
else:
    cleaned_df = st.session_state.cleaned_df
    cleaning_log = st.session_state.cleaning_log
    original_shape = st.session_state.original_shape

df = cleaned_df
n_rows, n_cols = df.shape
missing_count = int(df.isna().sum().sum())
duplicate_count = int(df.duplicated().sum())
score = quality_score(df)

# Top metrics
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Rows", f"{n_rows:,}", delta=f"{n_rows - original_shape[0]:+,} after cleaning")
m2.metric("Columns", f"{n_cols:,}")
m3.metric("Missing cells", f"{missing_count:,}")
m4.metric("Remaining duplicates", f"{duplicate_count:,}")
m5.metric("Data quality score", f"{score:.1f}/100")

tabs = st.tabs(["📋 Overview", "🧹 Cleaning report", "📈 Analysis & charts", "🔍 Data explorer", "⬇️ Export"])

with tabs[0]:
    st.subheader("Dataset preview")
    st.caption(f"File: **{uploaded.name}** · Showing first 100 rows")
    st.dataframe(df.head(100), use_container_width=True, height=360)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Column types")
        type_df = pd.DataFrame({"Column": df.columns, "Data type": [str(x) for x in df.dtypes], "Missing": df.isna().sum().values})
        st.dataframe(type_df, use_container_width=True, hide_index=True)
    with right:
        st.markdown("#### Missing values by column")
        missing_df = df.isna().sum().reset_index()
        missing_df.columns = ["Column", "Missing"]
        missing_df = missing_df[missing_df["Missing"] > 0].sort_values("Missing", ascending=False)
        if missing_df.empty:
            st.success("No missing values remain.")
        else:
            fig = px.bar(missing_df, x="Missing", y="Column", orientation="h", title="Missing cells")
            fig.update_layout(height=320, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)

with tabs[1]:
    st.subheader("Automatic cleaning report")
    st.write(f"Original dataset: **{original_shape[0]:,} rows × {original_shape[1]:,} columns**")
    st.write(f"Cleaned dataset: **{n_rows:,} rows × {n_cols:,} columns**")
    for entry in cleaning_log:
        st.markdown(f"- {entry}")
    st.divider()
    st.markdown("#### Data quality checks")
    checks = pd.DataFrame([
        {"Check": "Missing values", "Result": f"{missing_count:,}", "Status": "Pass" if missing_count == 0 else "Review"},
        {"Check": "Duplicate rows", "Result": f"{duplicate_count:,}", "Status": "Pass" if duplicate_count == 0 else "Review"},
        {"Check": "Completely empty rows", "Result": f"{int(df.isna().all(axis=1).sum()):,}", "Status": "Pass" if not df.isna().all(axis=1).any() else "Review"},
    ])
    st.dataframe(checks, hide_index=True, use_container_width=True)
    st.warning("Cleaning is rule-based. Review the log and sample rows before using the dataset for important decisions.")

with tabs[2]:
    st.subheader("Automatic analysis")
    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "string", "category", "bool"]).columns.tolist()

    if numeric_cols:
        st.markdown("#### Numerical summary")
        st.dataframe(df[numeric_cols].describe().T.reset_index().rename(columns={"index": "Column"}), use_container_width=True)
        selected_num = st.selectbox("Choose a numerical column", numeric_cols, key="num_chart")
        chart_type = st.selectbox("Chart type", ["Histogram", "Box plot"], key="num_type")
        if chart_type == "Histogram":
            fig = px.histogram(df, x=selected_num, nbins=30, title=f"Distribution of {selected_num}")
        else:
            fig = px.box(df, y=selected_num, points="outliers", title=f"Outliers in {selected_num}")
        st.plotly_chart(fig, use_container_width=True)

        # Correlation heatmap for at least two numeric columns
        if len(numeric_cols) >= 2:
            st.markdown("#### Correlation heatmap")
            corr = df[numeric_cols].corr(numeric_only=True)
            fig = px.imshow(corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r",
                            title="Correlation between numerical columns", zmin=-1, zmax=1)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Correlation indicates association, not causation.")
    else:
        st.info("No numerical columns were detected. Add numeric fields to enable statistical charts.")

    if categorical_cols:
        st.markdown("#### Category distribution")
        cat_col = st.selectbox("Choose a category column", categorical_cols, key="cat_chart")
        top_n = st.slider("Categories to display", 3, 20, 10)
        counts = df[cat_col].astype("string").fillna("(Missing)").value_counts().head(top_n).reset_index()
        counts.columns = [cat_col, "Count"]
        fig = px.bar(counts, x=cat_col, y="Count", title=f"Top categories in {cat_col}")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Potential outliers (IQR method)")
    if numeric_cols:
        outlier_rows = []
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue
            q1, q3 = series.quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr == 0:
                count = int((series != series.median()).sum())
            else:
                count = int(((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum())
            outlier_rows.append({"Column": col, "Potential outliers": count})
        if outlier_rows:
            st.dataframe(pd.DataFrame(outlier_rows), hide_index=True, use_container_width=True)
            st.caption("Outliers are flagged for review and are not automatically deleted.")
    else:
        st.caption("No numerical columns available for outlier checks.")

with tabs[3]:
    st.subheader("Data explorer")
    st.caption("Filter rows and inspect values. Filters affect the preview only, not the exported cleaned dataset.")
    filtered = df.copy()
    filter_cols = st.multiselect("Filter columns", list(df.columns))
    for col in filter_cols:
        if pd.api.types.is_numeric_dtype(filtered[col]):
            valid = filtered[col].dropna()
            if valid.empty:
                continue
            min_val, max_val = float(valid.min()), float(valid.max())
            if min_val == max_val:
                st.write(f"**{col}**: all values are {min_val:g}")
            else:
                low, high = st.slider(f"{col} range", min_val, max_val, (min_val, max_val), key=f"filter_{col}")
                filtered = filtered[filtered[col].between(low, high) | filtered[col].isna()]
        else:
            options = sorted(filtered[col].dropna().astype(str).unique().tolist())
            chosen = st.multiselect(f"{col} values", options, default=options[:min(10, len(options))], key=f"filter_{col}")
            if chosen:
                filtered = filtered[filtered[col].astype(str).isin(chosen) | filtered[col].isna()]
    st.write(f"Filtered rows: **{len(filtered):,}**")
    st.dataframe(filtered, use_container_width=True, height=420)

with tabs[4]:
    st.subheader("Download your results")
    st.write("Export the cleaned dataset and a record of the automated actions.")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Download cleaned CSV", data=make_csv(df),
                         file_name="cleaned_data.csv", mime="text/csv", use_container_width=True)
    with c2:
        st.download_button("⬇️ Download cleaned Excel", data=make_excel(df),
                         file_name="cleaned_data.xlsx",
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         use_container_width=True)
    log_text = "\n".join([
        f"Smart Data Analyzer cleaning report",
        f"Source file: {uploaded.name}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Original shape: {original_shape[0]} rows x {original_shape[1]} columns",
        f"Cleaned shape: {df.shape[0]} rows x {df.shape[1]} columns",
        f"Quality score: {score}/100",
        "",
        "Actions:",
        *[f"- {x}" for x in cleaning_log],
    ])
    st.download_button("📄 Download cleaning log", data=log_text.encode("utf-8"),
                      file_name="cleaning_report.txt", mime="text/plain", use_container_width=True)
    st.caption("Tip: Keep the original file separately. Cleaning can change values based on your selected rules.")

st.markdown("---")
st.caption("Smart Data Analyzer · Local-first prototype · Review automated changes before relying on results")
