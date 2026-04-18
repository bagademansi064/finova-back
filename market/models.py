from django.db import models

class StockCache(models.Model):
    """
    Local database cache for Yahoo Finance logic.
    Provides sub-second retrieval times and prevents API rate limits.
    """
    symbol = models.CharField(max_length=20, primary_key=True, help_text="e.g. AAPL, TSLA, RELIANCE.NS")
    
    current_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    previous_close = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    day_high = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    day_low = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    open_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    volume = models.BigIntegerField(null=True, blank=True)
    
    avg_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    last_qty = models.IntegerField(null=True, blank=True)
    ltq_time = models.CharField(max_length=20, null=True, blank=True)
    
    percent_change = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    
    # --- Zerodha-Style Fundamentals ---
    market_cap = models.BigIntegerField(null=True, blank=True)
    pe_ratio = models.FloatField(null=True, blank=True)
    pb_ratio = models.FloatField(null=True, blank=True)
    eps = models.FloatField(null=True, blank=True)
    book_value = models.FloatField(null=True, blank=True)
    
    beta = models.FloatField(null=True, blank=True)
    roe = models.FloatField(null=True, blank=True)
    roce = models.FloatField(null=True, blank=True)
    debt_to_equity = models.FloatField(null=True, blank=True)
    dividend_yield = models.FloatField(null=True, blank=True)
    
    sector = models.CharField(max_length=100, null=True, blank=True)
    industry = models.CharField(max_length=100, null=True, blank=True)
    
    # --- News ---
    news_data = models.JSONField(null=True, blank=True, default=dict, help_text="Stored news items array")
    
    last_updated = models.DateTimeField(auto_now=True)
    fundamentals_last_updated = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.symbol} - {self.current_price}"

    class Meta:
        verbose_name = 'Stock Cache'
        verbose_name_plural = 'Stock Caches'
        ordering = ['symbol']
