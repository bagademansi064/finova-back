from rest_framework import serializers
from .models import StockCache

class StockCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCache
        fields = '__all__'
