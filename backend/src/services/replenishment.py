from math import ceil, sqrt
from datetime import date, timedelta

def forecast_replenishment(daily_sales, on_hand, lead_time_days, safety_days, pack_size, expiry_date=None, substitute_sku=None, today='2026-11-21'):
    values=[float(v) for v in daily_sales[-7:]]
    if not values: raise ValueError('销量历史不能为空')
    avg=sum(values)/len(values)
    variance=sum((v-avg)**2 for v in values)/len(values)
    std=sqrt(variance)
    safety=max(avg*float(safety_days), std*1.65)
    reorder=avg*int(lead_time_days)+safety
    target=avg*(int(lead_time_days)+int(float(safety_days)))
    qty=max(0, ceil(max(0, reorder+target-float(on_hand))/int(pack_size))*int(pack_size))
    conflict=False
    if expiry_date and substitute_sku:
        try: conflict=date.fromisoformat(expiry_date) <= date.fromisoformat(today)+timedelta(days=30)
        except ValueError: conflict=True
    reason='临期且存在可替代品，需人工改写' if conflict else f'近{len(values)}日移动平均 {avg:.1f}，安全库存 {safety:.1f}'
    return {'avg_daily':round(avg,2),'safety_stock':round(safety,2),'reorder_point':round(reorder,2),'recommended_qty':qty,'blocked':conflict,'reason':reason}
