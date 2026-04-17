from rest_framework import views, status
from rest_framework.response import Response
from .models import StockCache
from .serializers import StockCacheSerializer
import yfinance as yf
from decimal import Decimal
from django.utils import timezone

class MarketDataView(views.APIView):
    """
    Retrieve real-time market data instantly without hitting Yahoo Finance limits.
    You can query by passing a comma-separated list of symbols:
    GET /api/market/live/?symbols=AAPL,MSFT,TSLA
    """
    def get(self, request):
        symbols_param = request.query_params.get('symbols', None)
        
        if symbols_param:
            raw_symbols = [s.strip().upper() for s in symbols_param.split(',')]
            # Force Indian suffix formatting
            symbols = [s if (s.endswith('.NS') or s.endswith('.BO')) else s + '.NS' for s in raw_symbols]
            
            stocks = list(StockCache.objects.filter(symbol__in=symbols))
            found_symbols = [stock.symbol for stock in stocks]
            
            missing_symbols = set(symbols) - set(found_symbols)
            
            # Synchronously fetch missing symbols so the user instantly gets what they searched for
            if missing_symbols:
                for target_sym in missing_symbols:
                    try:
                        ticker = yf.Ticker(target_sym)
                        info = ticker.info
                        if info and 'currentPrice' in info:
                            new_stock = StockCache.objects.create(
                                symbol=target_sym,
                                current_price=Decimal(str(info.get('currentPrice', 0.0))),
                                previous_close=Decimal(str(info.get('previousClose', 0.0))),
                                day_high=Decimal(str(info.get('dayHigh', 0.0))),
                                day_low=Decimal(str(info.get('dayLow', 0.0))),
                                volume=info.get('volume', 0),
                                market_cap=info.get("marketCap"),
                                pe_ratio=info.get("trailingPE"),
                                pb_ratio=info.get("priceToBook"),
                                sector=info.get("sector"),
                                industry=info.get("industry")
                            )
                            # Calculate percent change inline
                            if new_stock.previous_close and new_stock.previous_close > 0:
                                new_stock.percent_change = ((new_stock.current_price - new_stock.previous_close) / new_stock.previous_close) * Decimal('100.0')
                                new_stock.save(update_fields=['percent_change'])
                                
                            stocks.append(new_stock)
                    except Exception:
                        pass # Ignore if ticker does not exist in Yahoo Finance
        else:
            stocks = StockCache.objects.all()
            
        serializer = StockCacheSerializer(stocks, many=True)
        
        # Organize the JSON response natively by symbol for frontend convenience
        # Example: {"AAPL": { "current_price": ... }, "MSFT": { ... } }
        formatted_data = {
            item['symbol']: item for item in serializer.data
        }
        
        return Response(formatted_data, status=status.HTTP_200_OK)
