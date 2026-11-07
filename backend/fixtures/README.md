# Small synthetic platform fixtures

These CSVs contain the first three complete orders per platform store selected from the
repository's generated platform reports. DoorDash has six orders / ten lines; Grubhub has
six orders / eleven lines. Both are synthetic and do not establish actual provider guarantees.

The tests create additional cases for repeated dishes, modifiers, corrected complete orders,
invalid rows, missing optional values, identifiers, and time boundaries without changing
these baseline files or the full dataset. Import these fixtures with both `--synthetic`
and `--complete-orders`.
