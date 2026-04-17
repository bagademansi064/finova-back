from django.urls import path
from .views import MarketDataView

urlpatterns = [
    path('live/', MarketDataView.as_view(), name='market_live_data'),
]
