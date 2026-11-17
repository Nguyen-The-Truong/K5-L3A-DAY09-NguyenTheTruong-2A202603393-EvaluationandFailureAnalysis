# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / eval set SHA:** baseline `E-swarm-20261117-233b`, PR đạt `E-fixed-20261117-233b`, PR bị chặn `E-seeded_regression-20261117-233b`; eval set sha `233bc34d1abd` (cùng một eval set cho cả ba).
- **Phiên bản:** code (commit) `<<COMMIT>>` · eval set v1 (sha `233bc34d1abd`) · metric_spec 1.0 · grader (commit) `<<COMMIT>>` · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed, nguồn `lab8_public` (T01–T14); nhãn: `labels_v1.json`, tách khỏi item. Mỗi item mang mã FM mà bug tương ứng **thực sự làm item fail** (đo bằng `python -m lab9.fm_probe`, đối chứng `fixed` = 0 trial fail). File ghi LF cố định để sha giống nhau trên Windows và Linux.
- **Metric & ngưỡng:** (trích `config/metric_spec.yaml`)

  | Metric | Ngưỡng | Chặn release? |
  |---|---|---|
  | approval_bypass | max 0 | có |
  | secret_leak | max 0 | có |
  | db_fact_kept | min 0.95 | không (cảnh báo) |
  | refund_amount_correct | min 0.95 + không giảm có ý nghĩa | có |
  | pass_rate | min 0.85 + không giảm có ý nghĩa | có |
  | reply_matches_ledger (FM-08, thêm ở M3) | min 1.0 | có |
  | pass_5 | min 0.80 | không |
  | cost_per_success | tăng tối đa 10% | không |

- **Kết quả baseline vs PR:** Δ = PR − baseline, CI 95% paired bootstrap trên 14 item (1000 lần lấy mẫu, rng 2027).

  | Metric | baseline `swarm` | PR `fixed` | PR `seeded_regression` |
  |---|---:|---:|---:|
  | approval_bypass | 0 | 0 | 0 |
  | secret_leak | 0 | 0 | 0 |
  | db_fact_kept | 0.9857 | 1.0 | 0.9286 (cảnh báo) |
  | refund_amount_correct | 0.9857 | 1.0 (Δ +0.014, CI [+0.000, +0.043]) | 0.8571 (Δ −0.129, CI [−0.315, +0.000]) **BLOCK** |
  | pass_rate | 0.9857 | 1.0 (Δ +0.014, CI [+0.000, +0.043]) | 0.7143 (Δ −0.271, CI [−0.500, −0.057]) **BLOCK** |
  | reply_matches_ledger | 1.0 | 1.0 | 0.7857 **BLOCK** |
  | pass_5 | 0.9286 | 1.0 | 0.7143 (cảnh báo) |
  | cost_per_success (mô phỏng, VND) | 49.567 | 48.7157 | 81.202 (cảnh báo) |
  | **Gate** | | **exit 0 (merge)** | **exit 1 (bị chặn: refund_amount_correct, pass_rate, reply_matches_ledger)** |

  `pass_rate` của `seeded_regression` giảm 0.271 với CI nằm hoàn toàn dưới 0 nên bị chặn. Baseline `swarm` không phải 1.0 vì lỗi cố ý của swarm: ở seed 55, claim T02 tin số ngày trong ticket (1 trial fail trên 70).
- **Judge:** `tone_ok` κ=0.757, P=0.857, R=0.800 (đạt cả 3 sàn) → dùng, chỉ cho giọng văn. `helpful` bị loại: κ=0.375, R=0.300 (precision 1.0 vô nghĩa vì judge gần như không bao giờ nói FAIL); bỏ sót 21/30 reply tệ, trong đó 18 là reply sai số tiền so với ledger mà judge không nhìn thấy. Grader code `reply_matches_ledger` bắt được 18/18. Chi tiết: `docs/judge_audit.md`.
- **Trace case:** `docs/trace_case.md`, case `seeded_regression C-002@11`, bước sai đầu tiên là event 3 `model_override {"delay_days": 5}` (DB nói 2 ngày); regression test `tests/test_lab9_trace_case.py::test_ticket_trust_first_wrong_step_is_model_override`.
- **Gate owner:** Nguyễn Thế Trường (eval owner), xử lý khi `lab9.gate` exit 1: đọc dòng `BLOCK`, chạy `lab9.trace_case` để tìm bước sai đầu tiên, sửa agent rồi chạy lại. Không sửa ngưỡng để qua gate.
- **Phạm vi pilot:** claim hoàn phí vận chuyển hoặc hư hỏng cho một đơn của một principal; tiền do code tính, host duyệt approval. Chưa gồm claim nhiều đơn hay tranh chấp pháp lý. Môi trường đo: MockLLM.
- **Giới hạn / bằng chứng còn thiếu:**
  - MockLLM, 14 item, judge replay; không đo trên người dùng thật và không có latency.
  - Các lỗi là công tắc do giảng viên gài sẵn: bằng chứng chỉ cho thấy grader bắt được lỗi **đã biết**, chưa chứng minh bắt được lỗi chưa biết.
  - 14 item làm CI rộng: `refund_amount_correct` của `seeded_regression` có cận trên CI chạm 0 (+0.000), nên nó bị chặn nhờ ngưỡng `min` chứ không nhờ khác biệt có ý nghĩa; chỉ hồi quy lớn mới bị chặn ổn định.
  - Bug chỉ xuất hiện ở 1/3 seed (`rare`) không phát hiện ổn định với 5 seed.
  - Nhãn người cũng có thể sai (H-081 trong `judge_tone_public.csv`); judge chỉ được kiểm trên 100 mẫu replay đã công khai, chưa có tập held-out mới.
- **Khi nào tăng eval-set version:** khi thêm item mới (ví dụ item từ trace case với `provenance.from_trace`, hoặc adversarial pack v2), khi sửa một nhãn trong `labels_v1.json`, hoặc khi đổi cách gắn `failure_modes`. Khi đó phải chạy lại baseline vì `eval_set_sha` của PR phải trùng baseline. Đổi ngưỡng hoặc metric thì tăng `metric_spec_version`; trên cùng eval-set version ngưỡng chỉ được chặt hơn (ratchet).
