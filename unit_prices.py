"""Default unit prices based on Pennington Ridge / Upstate SC market (2026).

Calibrated against actual bid data from Pennington Ridge Subdivision
(Clear Path Development, Fountain Inn SC — $965K direct subtotal, 2025-2026).
"""

DEFAULT_SECTIONS = {
    "Earthwork": [
        {"Item": "EW-1", "Description": "Clearing & Grubbing", "Unit": "AC", "Qty": 0, "Unit Price": 5500.00},    # was 6500, actual range 4500-6500
        {"Item": "EW-2", "Description": "Mass Excavation/Fill", "Unit": "CY", "Qty": 0, "Unit Price": 5.00},      # Pennington actual
        {"Item": "EW-3", "Description": "Topsoil Strip & Stockpile", "Unit": "CY", "Qty": 0, "Unit Price": 2.50}, # Pennington actual
        {"Item": "EW-4", "Description": "Topsoil Respread", "Unit": "CY", "Qty": 0, "Unit Price": 3.00},          # Pennington actual
        {"Item": "EW-5", "Description": "Fine Grade Subgrade", "Unit": "SY", "Qty": 0, "Unit Price": 0.75},       # Pennington actual
        {"Item": "EW-6", "Description": "Proof Rolling", "Unit": "SY", "Qty": 0, "Unit Price": 0.40},             # was 0.50, typical 0.35-0.50
        {"Item": "EW-7", "Description": "Import/Export Haul", "Unit": "CY", "Qty": 0, "Unit Price": 6.50},        # was 8.00, depends on haul distance
    ],
    "Erosion Control": [
        {"Item": "EC-1", "Description": "Construction Entrance", "Unit": "EA", "Qty": 0, "Unit Price": 2200.00},  # was 2500, typical 1800-2500
        {"Item": "EC-2", "Description": "Silt Fence w/ J-hooks", "Unit": "LF", "Qty": 0, "Unit Price": 3.50},     # was 4.25, typical 3.00-4.25
        {"Item": "EC-3", "Description": "Inlet Protection", "Unit": "EA", "Qty": 0, "Unit Price": 175.00},        # was 225, typical 150-225
        {"Item": "EC-4", "Description": "Erosion Control Matting", "Unit": "SY", "Qty": 0, "Unit Price": 1.40},    # was 1.60, typical 1.25-1.75
        {"Item": "EC-5", "Description": "Temporary Seeding & Mulch", "Unit": "AC", "Qty": 0, "Unit Price": 1800.00}, # was 2000
        {"Item": "EC-6", "Description": "Permanent Seeding", "Unit": "AC", "Qty": 0, "Unit Price": 3000.00},      # was 3500, typical 2500-3500
    ],
    "Storm Drainage": [
        {"Item": "SD-1", "Description": '15" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 75.00},       # was 85, typical 65-85
        {"Item": "SD-2", "Description": '18" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 90.00},       # was 105, typical 80-105
        {"Item": "SD-3", "Description": '24" RCP Storm Pipe', "Unit": "LF", "Qty": 0, "Unit Price": 125.00},      # was 145, typical 110-145
        {"Item": "SD-4", "Description": "Catch Basin / Inlet", "Unit": "EA", "Qty": 0, "Unit Price": 3200.00},    # was 3800, typical 2800-3800
        {"Item": "SD-5", "Description": "Storm Manhole", "Unit": "EA", "Qty": 0, "Unit Price": 3800.00},          # was 4500, typical 3500-4500
        {"Item": "SD-6", "Description": "Headwall / Endwall w/ Riprap", "Unit": "EA", "Qty": 0, "Unit Price": 3500.00}, # was 4000
        {"Item": "SD-7", "Description": "Outlet Control Structure", "Unit": "EA", "Qty": 0, "Unit Price": 7500.00},    # was 9500
        {"Item": "SD-8", "Description": "Pond Excavation", "Unit": "CY", "Qty": 0, "Unit Price": 6.00},          # was 8.00, less than road excavation
        {"Item": "SD-9", "Description": "Pond Grading", "Unit": "SY", "Qty": 0, "Unit Price": 1.25},             # was 1.50
    ],
    "Sanitary Sewer": [
        {"Item": "SS-1", "Description": '8" PVC Sanitary Sewer', "Unit": "LF", "Qty": 0, "Unit Price": 40.00},    # was 45, typical 35-48
        {"Item": "SS-2", "Description": "Sanitary Manhole (4' Dia.)", "Unit": "EA", "Qty": 0, "Unit Price": 3800.00}, # was 4200
        {"Item": "SS-3", "Description": '4" Sewer Service Lateral', "Unit": "EA", "Qty": 0, "Unit Price": 1200.00},   # was 1500, typical 1000-1500
        {"Item": "SS-4", "Description": "Connect to Existing Sewer", "Unit": "EA", "Qty": 0, "Unit Price": 2500.00},  # was 3000
    ],
    "Water": [
        {"Item": "W-1", "Description": '8" DIP Water Main', "Unit": "LF", "Qty": 0, "Unit Price": 45.00},         # was 50, typical 40-55
        {"Item": "W-2", "Description": "Fire Hydrant Assembly", "Unit": "EA", "Qty": 0, "Unit Price": 4000.00},    # was 4500, typical 3500-4500
        {"Item": "W-3", "Description": "Gate Valve & Box", "Unit": "EA", "Qty": 0, "Unit Price": 1600.00},         # was 2000, typical 1400-2000
        {"Item": "W-4", "Description": "Tapping Sleeve & Valve", "Unit": "EA", "Qty": 0, "Unit Price": 3000.00},   # was 3500
        {"Item": "W-5", "Description": '3/4" Water Service & Meter', "Unit": "EA", "Qty": 0, "Unit Price": 1500.00}, # was 1800, typical 1200-1800
    ],
    "Paving & Concrete": [
        {"Item": "PC-1", "Description": 'Asphalt Base Course (2")', "Unit": "SY", "Qty": 0, "Unit Price": 18.00},  # was 20, typical 16-22
        {"Item": "PC-2", "Description": 'Asphalt Surface Course (1.5")', "Unit": "SY", "Qty": 0, "Unit Price": 22.00}, # was 26, typical 18-26
        {"Item": "PC-3", "Description": "Curb & Gutter (24\")", "Unit": "LF", "Qty": 0, "Unit Price": 26.00},      # Pennington actual
        {"Item": "PC-4", "Description": '4" Concrete Sidewalk', "Unit": "SF", "Qty": 0, "Unit Price": 8.00},       # was 9.50, typical 7-10
        {"Item": "PC-5", "Description": "ADA Ramp", "Unit": "EA", "Qty": 0, "Unit Price": 1000.00},                # was 1200, typical 800-1200
        {"Item": "PC-6", "Description": "Driveway Apron", "Unit": "EA", "Qty": 0, "Unit Price": 3000.00},          # was 8500! Residential ~2500-3500
    ],
    "Striping & Signage": [
        {"Item": "ST-1", "Description": '4" Thermoplastic Striping', "Unit": "LF", "Qty": 0, "Unit Price": 0.90},  # was 1.10, typical 0.75-1.10
        {"Item": "ST-2", "Description": "Stop Bar (24\")", "Unit": "EA", "Qty": 0, "Unit Price": 350.00},          # was 450
        {"Item": "ST-3", "Description": "Pavement Arrows", "Unit": "EA", "Qty": 0, "Unit Price": 250.00},          # was 300
        {"Item": "ST-4", "Description": "Regulatory Signs (Stop, Street)", "Unit": "EA", "Qty": 0, "Unit Price": 350.00}, # was 400
    ],
    "Fencing & Misc": [
        {"Item": "FM-1", "Description": "6' Chain Link Fence", "Unit": "LF", "Qty": 0, "Unit Price": 28.00},      # was 32, typical 25-35
        {"Item": "FM-2", "Description": "12' Swing Gate", "Unit": "EA", "Qty": 0, "Unit Price": 1500.00},          # was 1800
        {"Item": "FM-3", "Description": "Mobilization", "Unit": "LS", "Qty": 1, "Unit Price": 0.00},
        {"Item": "FM-4", "Description": "Bonds & Insurance", "Unit": "LS", "Qty": 1, "Unit Price": 0.00},
    ],
}
