import yfinance as yf
import pandas as pd
from decimal import Decimal
from django.db import transaction
from .models import StockCache
from groups.models import Discussion
import logging

logger = logging.getLogger(__name__)

def sync_market_data():
    """
    Background job to fetch real-time data from Yahoo Finance efficiently.
    Gathers all active symbols required by the platform and performs a single 
    bulk download to prevent API bans.
    """
    try:
        # 1. Gather all active symbols
        # Get from active discussions
        active_discussions = Discussion.objects.filter(
            status__in=['open', 'pooling', 'voting']
        ).values_list('stock_symbol', flat=True).distinct()
        
        # Ensure all symbols have Indian exchange suffixes (.NS or .BO)
        symbols_set = set()
        for sym in active_discussions:
            sym = sym.upper()
            if not sym.endswith('.NS') and not sym.endswith('.BO'):
                sym += '.NS'
            symbols_set.add(sym)
        
        # Also always track NIFTY top 20 anchors if it's empty
        if not symbols_set:
            symbols_set = {
                'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS',
                'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 'BAJFINANCE.NS',
                'HINDUNILVR.NS', 'KOTAKBANK.NS', 'AXISBANK.NS', 'ASIANPAINT.NS',
                'M&M.NS', 'MARUTI.NS', 'TITAN.NS', 'SUNPHARMA.NS', 'WIPRO.NS', 'HCLTECH.NS'
            }
            
        symbols_list = list(symbols_set)
        symbols_string = " ".join(symbols_list)
        
        # 2. Bulk Download from Yahoo Finance
        # period="5d" ensures we have previous close data to calculate day changes safely
        df = yf.download(symbols_string, period="5d", group_by="ticker", threads=True, progress=False)
        
        if df.empty:
            logger.warning("YFinance returned empty dataframe.")
            return

        with transaction.atomic():
            for symbol in symbols_list:
                try:
                    # Handle single ticker vs multi-ticker dataframe structure differences
                    if len(symbols_list) == 1:
                        ticker_df = df
                    else:
                        if symbol not in df.columns.levels[0]:
                            continue
                        ticker_df = df[symbol]
                        
                    # Drop NaN rows (e.g., weekends)
                    ticker_df = ticker_df.dropna()
                    if ticker_df.empty or len(ticker_df) < 2:
                        continue
                        
                    latest_row = ticker_df.iloc[-1]
                    prev_row = ticker_df.iloc[-2]
                    
                    current_price = Decimal(str(latest_row.get('Close', 0.0)))
                    prev_close = Decimal(str(prev_row.get('Close', 0.0)))
                    day_high = Decimal(str(latest_row.get('High', 0.0)))
                    day_low = Decimal(str(latest_row.get('Low', 0.0)))
                    volume = int(latest_row.get('Volume', 0))
                    
                    if prev_close > 0:
                        pct_change = ((current_price - prev_close) / prev_close) * Decimal('100.0')
                    else:
                        pct_change = Decimal('0.0')

                    StockCache.objects.update_or_create(
                        symbol=symbol,
                        defaults={
                            'current_price': current_price,
                            'previous_close': prev_close,
                            'day_high': day_high,
                            'day_low': day_low,
                            'volume': volume,
                            'percent_change': pct_change
                        }
                    )
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                    
        print(f"Fast-Synced {len(symbols_list)} stocks gracefully.")

    except Exception as e:
        logger.error(f"Failed critical market sync: {e}")

def sync_market_fundamentals():
    """
    Heavy Pacer: Fetches Zerodha-style fundamentals and news individually.
    Runs every 6 hours to avoid Yahoo Finance rate bans.
    """
    from django.utils import timezone
    
    try:
        active_discussions = Discussion.objects.filter(
            status__in=['open', 'pooling', 'voting']
        ).values_list('stock_symbol', flat=True).distinct()
        
        symbols_set = set()
        for sym in active_discussions:
            sym = sym.upper()
            if not sym.endswith('.NS') and not sym.endswith('.BO'):
                sym += '.NS'
            symbols_set.add(sym)
            
        if not symbols_set:
            symbols_set = {
                'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS',
                'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 'BAJFINANCE.NS',
                'HINDUNILVR.NS', 'KOTAKBANK.NS', 'AXISBANK.NS', 'ASIANPAINT.NS',
                'M&M.NS', 'MARUTI.NS', 'TITAN.NS', 'SUNPHARMA.NS', 'WIPRO.NS', 'HCLTECH.NS'
            }
            
        for symbol in symbols_set:
            try:
                company = yf.Ticker(symbol)
                info = company.info
                news = company.news
                
                # If yahoo returns completely empty info, it usually means bad symbol or rate limit
                if not info:
                    continue
                    
                StockCache.objects.update_or_create(
                    symbol=symbol,
                    defaults={
                        'market_cap': info.get("marketCap"),
                        'pe_ratio': info.get("trailingPE"),
                        'pb_ratio': info.get("priceToBook"),
                        'eps': info.get("trailingEps"),
                        'book_value': info.get("bookValue"),
                        'beta': info.get("beta"),
                        'roe': info.get("returnOnEquity"),
                        'roce': info.get("returnOnAssets"),
                        'debt_to_equity': info.get("debtToEquity"),
                        'dividend_yield': info.get("dividendYield"),
                        'sector': info.get("sector"),
                        'industry': info.get("industry"),
                        'news_data': news,
                        'fundamentals_last_updated': timezone.now()
                    }
                )
            except Exception as e:
                logger.error(f"Failed fundamental sync for {symbol}: {e}")
                
        print(f"Fundamentals Synced {len(symbols_set)} stocks successfully.")
        
    except Exception as e:
        logger.error(f"Failed critical fundamental sync: {e}")

