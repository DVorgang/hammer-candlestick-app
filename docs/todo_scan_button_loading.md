# TODO: Investigate Scan Button Loading Indicators

## Context

The manual scan buttons in the Scanner Control Hub should clearly show that work is happening after the user clicks them.

The buttons to review are:

- Run Instant Technical Scan
- Run Instant Market Growth Scan

## Current Concern

The loading state can be hard to notice or may not appear reliably before the scan begins. This is likely because Streamlit reruns the page, renders a loading marker, and then immediately starts a blocking scan operation.

## Follow-Up Investigation

- Confirm whether the loading indicator appears consistently on slower and faster machines.
- Compare the scan buttons with other buttons that use `st.spinner(...)`.
- Decide whether the scan buttons should use:
  - A compact custom spinner row.
  - Streamlit's built-in `st.spinner(...)`.
  - A disabled button state.
  - A progress/status placeholder.
- Avoid adding too much visual weight to the scanner controls.
- Ensure the UI communicates that the scan is running without pushing too much content down the page.

## Desired Outcome

When a user clicks a manual scan button, the UI should make it obvious that the scan is running while staying compact and visually clean.
