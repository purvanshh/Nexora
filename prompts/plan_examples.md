# Few-shot planning examples

## Primary: Acme invoice → finance

1. `api` GET `/api/mail` — list inbox, find newest Acme email with amount.
2. `api` GET `/api/mail/{id}` — extract amount, due_date, invoice_id.
3. `remember` each field into scratchpad.
4. `api` POST `/api/invoices` with sender, amount, due_date, invoice_id (all four).
5. On HTTP 500, the loop retries transient failures; if exhausted, escalate (retry/skip/abort).
6. Confirm via browser at `/finance/invoices`, then `finish` with summary of what was submitted.

## Secondary: employee payslip

1. `api` GET `/api/employees/42` — confirm employee exists.
2. `api` GET `/api/payslips/42` — read latest net_pay.
3. `remember` employee_id and net_pay.
4. `finish` with the net pay figure.
