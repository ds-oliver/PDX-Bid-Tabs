# Dashboard Field Mapping

Object-level mapping between ODOT report components and Port bid tabulation objects.
Includes all ODOT-highlighted objects and all extracted Port objects for completeness.

| ODOT Report Object | Port Data Object | Report Feature | Example (ODOT) | Example (Port) | Port Data Object Source | ODOT Example Source | Mapping Status | Dev Notes |
|---|---|---|---|---|---|---|---|---|
| Item | item | Table,Slicer | 251601020 - PARTIAL DEPTH PAVEMENT REPAIR (442) | 012200 - Sweeper | Best-guess derived business object from item description parsing | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Best Guess | Port requested follow-up: 'Let's talk about these after you look at the data.' Current Port equivalents/examples are best-guess mappings and not yet confirmed. |
| Specification | specification | Slicer | 250 Pavement Repairs | 012200 | Best-guess derived specification parsed from item description | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Best Guess | Port requested follow-up: 'Let's talk about these after you look at the data.' Current Port equivalents/examples are best-guess mappings and not yet confirmed. |
| Supplemental Description | supplemental_description | Slicer | All | 3' | Best-guess derived supplemental qualifier parsed from item description | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Best Guess | Port requested follow-up: 'Let's talk about these after you look at the data.' Current Port equivalents/examples are best-guess mappings and not yet confirmed. |
| District & County | location_name_raw | Slicer | All | HILLSBOROAIRPORT | Bid Tab Header: Location/Facility | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Quantity | quantity_raw | Table,Slicer | 1,172.00 | 1 | Line Item Column: Estimated Quantity | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Letting Date | letting_date_raw | Slicer | 2/27/2025 | 2026-02-02 | Bid Tab Header: Letting Date (Port business label: Advertise Date) | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Contractor | bidder_name_raw | Table,Slicer | GERKEN PAVING INC | K & E Excavating, Inc. | Bidder Header: Contractor label above Unit/Total columns | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Awarded Item Price | unit_price_raw | Table | $50.00 | 216000 | Bidder Columns: Unit Price | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Average Item Price | average_unit_price_top3 | Table | $94.00 | 157333.33 | Derived metric: mean of 3 lowest contractor unit prices | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Project Total | schedule_total_raw | Table | $7,150,446.13 | 10235723.8 | Totals Row: Total Amount Bid (Basis of Award) | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Unit | unit_code_raw | Table | SY | LS | Line Item Column: Units | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Item Description | item_description_raw | Table | PARTIAL DEPTH PAVEMENT REPAIR (442) | Sweeper (Section012200) | Line Item Column: Item Description | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Project Number | project_ean | Table | 250122 | 2019D031 | Bid Tab Header: EAN (Port business label: EAN) | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| CRS | project_name_raw | Table | HEN-SR 108/SR 109-16.57/00.00 Resurf (PART 1 AND PART 2) | RUNWAY 13R-31L AND RUNWAY SAFETY AREA IMPROVEMENTS | Bid Tab Header: Project Title (Port business label: Project Name) | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| Number of Bidders | number_of_bidders | Table | 1 | 3 | Derived metric: distinct contractor bidders by sheet/schedule | ODOT Item Price Search dashboard screenshot artifact (annotated by Port) | Mapped |  |
| NA | line_no | NA | NA | 0001 | Line Item Column: Item No. | NA | Port Only | Included for completeness/traceability; not in current dashboard requirements. |
| NA | solicitation_no | NA | NA | 2022-10081 | Bid Tab Header: Solicitation No. | NA | Port Only | Included for completeness/traceability; not in current dashboard requirements. |
| NA | total_price_raw | NA | NA | 216000 | Bidder Columns: Total Price | NA | Port Only | Included for completeness/traceability; not in current dashboard requirements. |
