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

## Leave write (second write-type task)

1. `api` GET `/api/employees/42` — confirm employee exists.
2. `remember` employee_id, leave_start, leave_end, leave_reason from the task text.
3. `api` POST `/api/leave` with API fields only:
   `{"employee_id":42,"start_date":"2025-04-01","end_date":"2025-04-05","reason":"family"}`
   (do not send leave_start/leave_end/leave_reason — that is a 422).
4. `finish` with the leave confirmation. No invoice POSTs.
