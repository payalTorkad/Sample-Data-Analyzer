<<<<<<< HEAD
# Smart Data Analyzer

A beginner-friendly Streamlit website for automatic data cleaning, exploratory analysis, charts, and exporting cleaned data.

## Features
- Upload CSV, Excel (`.xlsx`, `.xls`) or JSON datasets
- Standardize column names, trim whitespace, convert blank strings to missing values
- Infer numeric-like text columns
- Remove exact duplicate rows and completely empty rows
- Fill missing numeric/text values using configurable strategies
- Preview dataset and data types
- Summary statistics, histograms, box plots, category charts, correlation heatmap, and IQR outlier flags
- Export cleaned CSV, Excel, and a cleaning log

## Requirements
- Windows 10/11
- Python 3.10 or newer (Python 3.11 or 3.12 recommended)
- Internet connection for installing packages

## Run on Windows (PowerShell)
1. Extract the ZIP file.
2. Open the extracted `smart_data_analyzer` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

5. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run this only for the current terminal:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

   Or use Command Prompt instead:
   ```bat
   .venv\Scripts\activate.bat
   ```

6. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

7. Start the website:

   ```powershell
   python -m streamlit run app.py
   ```

8. Streamlit opens a browser page, usually `http://localhost:8501`. Upload your file in the sidebar.

## Notes / limitations
- This is rule-based data cleaning, not a magic AI model. It cannot know the correct business meaning of every column.
- Numeric missing-value filling can distort data. Review the cleaning log and original file.
- Exact duplicate rows are removed; near-duplicates (for example, spelling variations) are not automatically merged.
- Outliers are flagged, not deleted.
- The app processes files in the Streamlit server session. For a public deployment, add authentication, file-size limits, privacy notices, and secure storage controls before accepting sensitive data.
- Very large files may need chunked processing or a database-backed architecture.
=======
# Sample-Data-Analyzer
>>>>>>> a5cb6bda80b1dea3d3f4419715ecd6f7f0e70882
