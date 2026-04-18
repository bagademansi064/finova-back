import random
from rest_framework import views, status
from rest_framework.response import Response
from .models import StockCache
from .serializers import StockCacheSerializer
import yfinance as yf
from decimal import Decimal
from django.utils import timezone

def generate_mock_depth(price):
    if not price: return None
    price = float(price)
    bids = []
    offers = []
    for i in range(5):
        # Bids are slightly below current price
        bid_price = round(price - (0.05 * (i + 1)), 2)
        bids.append({
            "price": bid_price,
            "orders": random.randint(1, 40),
            "quantity": random.randint(100, 5000)
        })
        # Offers are slightly above
        offer_price = round(price + (0.05 * (i + 1)), 2)
        offers.append({
            "price": offer_price,
            "orders": random.randint(1, 40),
            "quantity": random.randint(100, 5000)
        })
    return {
        "bids": bids,
        "offers": offers,
        "total_bid_qty": sum(b["quantity"] for b in bids),
        "total_offer_qty": sum(o["quantity"] for o in offers)
    }

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
            # Force Indian suffix formatting unless it already has one or is a US stock
            symbols = []
            for s in raw_symbols:
                if '.' in s:
                    symbols.append(s)
                else:
                    # Default to .NS for Indian stocks if no suffix
                    symbols.append(s + '.NS')
            
            stocks = list(StockCache.objects.filter(symbol__in=symbols))
            found_symbols = [stock.symbol for stock in stocks]
            
            missing_symbols = set(symbols) - set(found_symbols)
            
            # Synchronously fetch missing symbols so the user instantly gets what they searched for
            if missing_symbols:
                for target_sym in missing_symbols:
                    try:
                        ticker = yf.Ticker(target_sym)
                        info = ticker.info
                        if info and ('currentPrice' in info or 'regularMarketPrice' in info):
                            price = info.get('currentPrice') or info.get('regularMarketPrice')
                            new_stock = StockCache.objects.create(
                                symbol=target_sym,
                                current_price=Decimal(str(price or 0.0)),
                                previous_close=Decimal(str(info.get('previousClose', 0.0))),
                                open_price=Decimal(str(info.get('open', 0.0))),
                                day_high=Decimal(str(info.get('dayHigh', 0.0))),
                                day_low=Decimal(str(info.get('dayLow', 0.0))),
                                volume=info.get('volume', 0),
                                avg_price=Decimal(str(info.get('averageDailyVolume10Day', 0))), # Mocking avg price if not found
                                last_qty=random.randint(1, 100),
                                ltq_time=timezone.now().strftime("%H:%M:%S"),
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
        # And inject mock market depth
        formatted_data = {}
        for item in serializer.data:
            symbol = item['symbol']
            item['market_depth'] = generate_mock_depth(item['current_price'])
            formatted_data[symbol] = item
            
        return Response(formatted_data, status=status.HTTP_200_OK)
