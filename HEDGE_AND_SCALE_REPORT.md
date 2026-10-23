# Báo cáo Thử nghiệm: Phòng vệ Hàng tồn Phái sinh (VN30F) & Tối ưu Scale Vốn

Dựa trên phản hồi và gợi ý của Advisor:
1. **Short phái sinh theo giá trị hàng tồn:** Tích lũy hàng tồn càng nhiều thì short càng nhiều, không cần đoán đỉnh đáy.
2. **Thử nghiệm scale vốn:** 500 triệu, 1 tỷ và 5 tỷ VND.
3. **Tối ưu bước grid:** Nâng số cấp grid (N = 18, 24, 30, 36) để tối ưu hiệu suất sử dụng vốn.

![Inventory Hedge Comparison](images/inventory_hedge_scale_comparison.png)

## 1. So sánh Hiệu quả Phòng vệ Hàng tồn (Vốn 1.0 Tỷ, N=18)

| Giai đoạn Thị trường | Chế độ Giao dịch | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Roundtrips Khớp | PnL Harvest Cơ sở | PnL Phái sinh VN30F |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| in_sample | Unhedged (Pure Spot Grid) | -11.47% | -40.61% | 0.071 | 890 | +262,036,062 VND | +0 VND |
| in_sample | Dynamic Inventory Hedge (VN30F) | -0.66% | -29.37% | 0.094 | 890 | +262,036,062 VND | +108,080,000 VND |
| out_sample | Unhedged (Pure Spot Grid) | +8.90% | -3.30% | 0.334 | 250 | +95,222,353 VND | +0 VND |
| out_sample | Dynamic Inventory Hedge (VN30F) | +6.51% | -3.27% | -0.037 | 250 | +95,222,353 VND | -23,880,000 VND |
| holdout | Unhedged (Pure Spot Grid) | +7.29% | -6.88% | 0.254 | 288 | +102,077,890 VND | +0 VND |
| holdout | Dynamic Inventory Hedge (VN30F) | +4.90% | -7.78% | 0.111 | 288 | +102,077,890 VND | -23,870,000 VND |

## 2. Thử nghiệm Scale Vốn (500M, 1B, 5B VND)

| Quy mô Vốn | Giai đoạn | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Tỷ lệ Vi phạm Lot 100 CP | PnL Harvest | PnL Phái sinh |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 500M VND | in_sample | +2.05% | -36.87% | 0.182 | 2.1% | +145,390,864 VND | +47,380,000 VND |
| 500M VND | holdout | +4.33% | -6.58% | 0.068 | 0.0% | +50,971,327 VND | -14,670,000 VND |
| 1.0B VND | in_sample | -0.66% | -29.37% | 0.094 | 0.0% | +262,036,062 VND | +108,080,000 VND |
| 1.0B VND | holdout | +4.90% | -7.78% | 0.111 | 0.0% | +102,077,890 VND | -23,870,000 VND |
| 5.0B VND | in_sample | -0.66% | -31.46% | 0.110 | 0.0% | +1,300,977,762 VND | +535,740,000 VND |
| 5.0B VND | holdout | +5.19% | -7.13% | 0.128 | 0.0% | +521,817,378 VND | -115,540,000 VND |

## 3. Thử nghiệm Tối ưu Số bước Grid (N = 18, 24, 30, 36)

| Quy mô Vốn | Số bước (N) | Spacing (%) | In-Sample Return | In-Sample MaxDD | Holdout Return | Holdout MaxDD | Holdout Roundtrips |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1.0B VND | 18 | 1.8% | -0.66% | -29.37% | +4.90% | -7.78% | 288 |
| 1.0B VND | 24 | 1.5% | -1.21% | -29.67% | -26.08% | -28.47% | 327 |
| 1.0B VND | 30 | 1.5% | -1.16% | -24.27% | -19.18% | -21.73% | 327 |
| 1.0B VND | 36 | 1.5% | +4.38% | -21.71% | -15.87% | -18.81% | 327 |
| 5.0B VND | 18 | 1.8% | -0.66% | -31.46% | +5.19% | -7.13% | 288 |
| 5.0B VND | 24 | 1.5% | -3.63% | -27.43% | -25.29% | -28.53% | 327 |
| 5.0B VND | 30 | 1.5% | -1.25% | -21.93% | -20.08% | -22.84% | 327 |
| 5.0B VND | 36 | 1.5% | +2.19% | -21.65% | -16.76% | -19.04% | 327 |
