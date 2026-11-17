# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: C-002@11 trên `seeded_regression` (FM-03 ticket_trust)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID trial `R-seeded_regression-C-002-s11`, nằm trong report `E-seeded_regression-20261117-233b` (`reports/eval_seeded_regression.json`) |
| Triệu chứng | Grader fail: `pass_rate` (Lab 8: `status resolved != denied`), `refund_amount_correct` (ledger 20.000, nhãn 0) và `db_fact_kept` (có event `model_override`). Reply nói "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." và ledger đúng là có 1 dòng 20.000 nên reply khớp ledger (`reply_matches_ledger` không bắt được), nhưng **khoản hoàn đó không được phép tồn tại**. |
| Bước sai đầu tiên | Bước **3**, kind `model_override`, payload `{"delay_days": 5}`. Dòng đơn trong DB (event 2, `lookup_order`) ghi `O-202 delivered delay_days=2`; ticket nói "trễ 5 ngày". |
| Vì sao là bước *đầu tiên* | Bước **1** `handoff` và bước **2** `investigator` đúng: đơn nhìn thấy được, `delay_days` đúng là 2. Bước **4** `quote` (20.000, clause `SHIP-LATE-03`) chỉ là hệ quả: `compute_compensation` tính đúng với đầu vào đã bị ghi đè. Bước **5** `refund_history` và bước **6** `reply` cũng chỉ lan truyền số sai. |
| Failure mode | **FM-03** (`docs/failure_taxonomy.md`). Hai lỗi khác của `seeded_regression` (FM-05 `pre_deducted`, FM-02 `ignore_denied`) không phải nguyên nhân ở case này vì `refund_history` trả 0 và host chấp nhận khoản hoàn. |
| Đối chứng | Cùng `C-002@11` trên `fixed`: không có event `model_override`; bước 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, bước 4 reply "chưa đủ điều kiện hoàn", status `denied`, ledger 0, Lab 8 grader `PASS`. |
| Regression test | `tests/test_lab9_trace_case.py::test_ticket_trust_first_wrong_step_is_model_override`. Test khẳng định: trên `seeded_regression` event thứ 3 là `model_override` với `delay_days` khác DB, `DbFactKept` và `RefundAmountCorrect` đều fail; trên `fixed` không có override và mọi grader sạch. Cũng đã thấy fail trên variant lỗi và pass trên `fixed` (2 nhánh trong cùng test). |
| Chưa chắc chắn | (1) Trace không cho biết **vì sao** agent chọn tin ticket: bản `seeded_regression` được gài cứng bằng công tắc `ticket_trust`, nên đây là lỗi do thiết kế của variant, chưa phải hành vi tự phát của một model thật. (2) Chỉ có seed 11 được xem kỹ; `ticket_trust` bật vô điều kiện nên fail 5/5 seed, còn swarm gốc chỉ dính ở seed chia hết cho 5 (T02 ở seed 55). (3) Một variant "im lặng" không để lại event `model_override` (`quiet_override`) sẽ qua mặt `db_fact_kept`, và chỉ `refund_amount_correct` bắt được. Vì vậy phải đọc **ledger trước reply và trước event**. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai. Ở case này reply khớp ledger, và chính ledger là nơi lộ ra lỗi.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
