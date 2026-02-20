"""Generate a construction bid estimate Excel workbook (TSC Liberty Bid).

Usage:
    python estimate_workbook.py [--output path/to/output.xlsx]
"""

import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Line-item definitions by section
# ---------------------------------------------------------------------------

BID_SECTIONS: Dict[str, List[dict]] = {
    "Earthwork": [
        {"Item": "EW-1", "Description": "Clearing & Grubbing", "Unit": "AC", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-2", "Description": "Unclassified Excavation (Cut)", "Unit": "CY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-3", "Description": "Embankment (Fill)", "Unit": "CY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-4", "Description": "Topsoil Strip & Stockpile", "Unit": "CY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-5", "Description": "Fine Grading", "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-6", "Description": "Proof Rolling", "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EW-7", "Description": "Import/Export Haul", "Unit": "CY", "Qty": 0, "Unit Price": 0.00},
    ],
    "Erosion Control": [
        {"Item": "EC-1", "Description": "Silt Fence", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EC-2", "Description": "Inlet Protection", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EC-3", "Description": "Construction Entrance", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EC-4", "Description": "Erosion Control Blanket", "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EC-5", "Description": "Temporary Seeding", "Unit": "AC", "Qty": 0, "Unit Price": 0.00},
        {"Item": "EC-6", "Description": "Permanent Seeding & Mulch", "Unit": "AC", "Qty": 0, "Unit Price": 0.00},
    ],
    "Storm Drainage": [
        {"Item": "SD-1", "Description": '15" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-2", "Description": '18" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-3", "Description": '24" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-4", "Description": "Storm Manhole (4\u2019 Dia.)", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-5", "Description": "Curb Inlet (Type A)", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-6", "Description": "Headwall / Endwall", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SD-7", "Description": "Detention Pond Grading", "Unit": "CY", "Qty": 0, "Unit Price": 0.00},
    ],
    "Water": [
        {"Item": "W-1", "Description": '8" DIP Water Main', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "W-2", "Description": '6" DIP Water Main', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "W-3", "Description": "Fire Hydrant Assembly", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "W-4", "Description": '8" Gate Valve & Box', "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "W-5", "Description": '3/4" Water Service & Meter', "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "W-6", "Description": "Connect to Existing Main", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
    ],
    "Sanitary Sewer": [
        {"Item": "SS-1", "Description": '8" PVC Sanitary Sewer', "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SS-2", "Description": "Sanitary Manhole (4\u2019 Dia.)", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SS-3", "Description": '4" Sewer Service Lateral', "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SS-4", "Description": "Connect to Existing Sewer", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "SS-5", "Description": "Trench Safety System", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
    ],
    "Paving & Concrete": [
        {"Item": "PC-1", "Description": '6" Lime-Stabilised Subgrade', "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-2", "Description": '8" Crushed Stone Base', "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-3", "Description": '2" HMAC Surface Course', "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-4", "Description": '2" HMAC Binder Course', "Unit": "SY", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-5", "Description": "Concrete Curb & Gutter", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-6", "Description": '4" Concrete Sidewalk', "Unit": "SF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-7", "Description": "ADA Ramp", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "PC-8", "Description": "Concrete Driveway Apron", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
    ],
    "Striping & Signage": [
        {"Item": "ST-1", "Description": "4\" Thermoplastic Striping", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "ST-2", "Description": "Stop Sign Assembly", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "ST-3", "Description": "Street Name Sign Assembly", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "ST-4", "Description": "Speed Limit Sign", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
    ],
    "Fencing & Misc": [
        {"Item": "FM-1", "Description": "6\u2019 Wood Privacy Fence", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "FM-2", "Description": "4\u2019 Chain-Link Fence", "Unit": "LF", "Qty": 0, "Unit Price": 0.00},
        {"Item": "FM-3", "Description": "Mailbox Kiosk (Cluster)", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "FM-4", "Description": "Bollard", "Unit": "EA", "Qty": 0, "Unit Price": 0.00},
        {"Item": "FM-5", "Description": "Mobilisation", "Unit": "LS", "Qty": 1, "Unit Price": 0.00},
        {"Item": "FM-6", "Description": "Bonds & Insurance", "Unit": "LS", "Qty": 1, "Unit Price": 0.00},
    ],
}


def generate_workbook(
    output_path: str = "TSC_Liberty_Bid_Estimate.xlsx",
    project_name: str = "TSC Liberty",
    sections: Optional[Dict[str, List[dict]]] = None,
) -> Path:
    """Create an Excel workbook with formatted bid estimate sheets.

    Args:
        output_path: Destination file path.
        project_name: Name shown in headers.
        sections: Override the default BID_SECTIONS dict.

    Returns:
        Path to the generated workbook.
    """
    sections = sections or BID_SECTIONS
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(str(out), engine="xlsxwriter") as writer:
        workbook = writer.book

        # Shared formats
        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#2F5496", "font_color": "#FFFFFF",
            "border": 1, "font_size": 11, "text_wrap": True,
        })
        currency_fmt = workbook.add_format({"num_format": "$#,##0.00", "border": 1})
        qty_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        text_fmt = workbook.add_format({"border": 1, "text_wrap": True})
        total_fmt = workbook.add_format({
            "bold": True, "num_format": "$#,##0.00", "border": 1,
            "bg_color": "#D6E4F0",
        })
        title_fmt = workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#2F5496",
        })

        all_rows: List[dict] = []

        for section_name, items in sections.items():
            # Truncate sheet name to 31 chars (Excel limit)
            sheet_name = section_name[:31]
            df = pd.DataFrame(items)
            df["Amount"] = df["Qty"] * df["Unit Price"]
            df.to_excel(writer, sheet_name=sheet_name, startrow=2, index=False)

            ws = writer.sheets[sheet_name]
            ws.write(0, 0, f"{project_name} — {section_name}", title_fmt)

            # Apply header format
            for col_idx, col_name in enumerate(df.columns):
                ws.write(2, col_idx, col_name, header_fmt)

            # Apply cell formats
            for row_idx in range(len(df)):
                excel_row = row_idx + 3
                ws.write(excel_row, 0, df.iloc[row_idx]["Item"], text_fmt)
                ws.write(excel_row, 1, df.iloc[row_idx]["Description"], text_fmt)
                ws.write(excel_row, 2, df.iloc[row_idx]["Unit"], text_fmt)
                ws.write(excel_row, 3, df.iloc[row_idx]["Qty"], qty_fmt)
                ws.write(excel_row, 4, df.iloc[row_idx]["Unit Price"], currency_fmt)
                ws.write(excel_row, 5, df.iloc[row_idx]["Amount"], currency_fmt)

            # Section total
            total_row = len(df) + 3
            ws.write(total_row, 4, "Section Total:", total_fmt)
            ws.write(total_row, 5, df["Amount"].sum(), total_fmt)

            # Column widths
            ws.set_column(0, 0, 8)
            ws.set_column(1, 1, 35)
            ws.set_column(2, 2, 8)
            ws.set_column(3, 3, 12)
            ws.set_column(4, 5, 16)

            for item in items:
                row = dict(item)
                row["Section"] = section_name
                row["Amount"] = row["Qty"] * row["Unit Price"]
                all_rows.append(row)

        # Summary sheet
        summary_data = []
        for section_name, items in sections.items():
            df_sec = pd.DataFrame(items)
            df_sec["Amount"] = df_sec["Qty"] * df_sec["Unit Price"]
            summary_data.append({
                "Section": section_name,
                "Line Items": len(items),
                "Section Total": df_sec["Amount"].sum(),
            })

        sdf = pd.DataFrame(summary_data)
        sdf.to_excel(writer, sheet_name="Summary", startrow=2, index=False)
        ws_sum = writer.sheets["Summary"]
        ws_sum.write(0, 0, f"{project_name} — Bid Summary", title_fmt)

        for col_idx, col_name in enumerate(sdf.columns):
            ws_sum.write(2, col_idx, col_name, header_fmt)

        for row_idx in range(len(sdf)):
            excel_row = row_idx + 3
            ws_sum.write(excel_row, 0, sdf.iloc[row_idx]["Section"], text_fmt)
            ws_sum.write(excel_row, 1, sdf.iloc[row_idx]["Line Items"], qty_fmt)
            ws_sum.write(excel_row, 2, sdf.iloc[row_idx]["Section Total"], currency_fmt)

        grand_total_row = len(sdf) + 3
        ws_sum.write(grand_total_row, 1, "Grand Total:", total_fmt)
        ws_sum.write(grand_total_row, 2, sdf["Section Total"].sum(), total_fmt)

        ws_sum.set_column(0, 0, 25)
        ws_sum.set_column(1, 1, 14)
        ws_sum.set_column(2, 2, 18)

    logger.info("Workbook saved to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate TSC Liberty Bid Estimate workbook")
    parser.add_argument("--output", "-o", default="TSC_Liberty_Bid_Estimate.xlsx", help="Output file path")
    parser.add_argument("--project", "-p", default="TSC Liberty", help="Project name")
    args = parser.parse_args()
    path = generate_workbook(output_path=args.output, project_name=args.project)
    print(f"Workbook generated: {path}")


if __name__ == "__main__":
    main()
