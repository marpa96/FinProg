# Rocket Money Extractors

This folder is for Rocket Money-specific extraction code.

Extractors should only pull raw data out of Rocket Money exports and preserve source context. They should not decide how rows become FinProg income, expenses, savings, categories, or forecasts.

Current starter:

```python
from extractors.rocket_money import RocketMoneyCsvExtractor

payload = RocketMoneyCsvExtractor().extract("rocket_money_export.csv")
print(payload.metadata)
```
