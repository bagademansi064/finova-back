import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.test import RequestFactory
from market.views import MarketDataView

def test():
    factory = RequestFactory()
    request = factory.get('/api/market/live/')
    view = MarketDataView.as_view()
    response = view(request)
    
    print("\n--- JSON OUTPUT RECEIVED BY FRONTEND ---\n")
    print(json.dumps(response.data, indent=4))
    
if __name__ == "__main__":
    test()
