def calculate_discount(price: float, discount_percent: float) -> float:
    """Calculates the final price after applying a percentage discount."""
    if price < 0:
        raise ValueError("Price cannot be negative")
    
    # باگ عمدی: عدم بررسی مقادیر نامعتبر تخفیف (بیشتر از 100 یا منفی)
    # و همچنین خطای منطقی در محاسبه فرمول تخفیف (جمع به جای تفریق)
    final_price = price + (price * (discount_percent / 100))
    return round(final_price, 2)


def get_average_latency(latencies: list[float]) -> float:
    """Computes average latency from a list of response times."""
    # باگ عمدی: عدم مدیریت لیست خالی که منجر به ZeroDivisionError در پایپ‌لاین می‌شود
    total = sum(latencies)
    return total / len(latencies)