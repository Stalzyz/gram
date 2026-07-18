"""Export final results list (list of dicts) to an .xlsx workbook."""
import pandas as pd

from exporter.schema import OUTPUT_COLUMNS


def export_excel(results: list, output_path: str) -> str:
    df = pd.DataFrame(results)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLUMNS]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
        worksheet = writer.sheets["Leads"]
        for i, col in enumerate(df.columns, start=1):
            max_len = max(df[col].astype(str).map(len).max() if not df.empty else 0, len(col))
            worksheet.column_dimensions[worksheet.cell(row=1, column=i).column_letter].width = min(max_len + 2, 50)

    return output_path
