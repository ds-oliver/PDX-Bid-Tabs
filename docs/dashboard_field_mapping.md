# Dashboard Field Mapping

Mappings reflect the Star Schema (Projects, Items, Bids) architecture.

| ODOT Report Field | Port Report Field Source | Port Report Field Name | Example Raw | Example Normalized |
|---|---|---|---|---|
| Specification | Items.Specification Code | Specification | (Item P-620) | P-620 |
| Item Description | Items.Item Description | Item Description | Marking (Item P-620) | Marking |
| Letting Date | Projects.Advertise Date | Advertise Date | 2/11/26 | 2026 |
| District & County | Projects.Location | Location | PORTLAND INTERNATIONAL AIRPORT | PDX |
| Project Number | Projects.EAN | EAN | EAN 2023D018 | 2023D018 |
| Quantity | Items.Estimated Quantity | Estimated Quantity | 163,800.0 | 163,800 |
| Unit | Items.Unit | Units | SY | SY |
| Awarded Unit Price | Bids.Unit Price (Filter: Is_Winner=True) | Unit Price | $2.93 | 2.93 |
| Contractor | Bids.Contractor Name | Contractor | American Road Maintenance | American Road Maintenance |
