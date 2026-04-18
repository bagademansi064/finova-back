from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Backfill individual_virtual_capital for existing users who have 0.00'

    def handle(self, *args, **options):
        users_to_fix = User.objects.filter(individual_virtual_capital=Decimal('0.00'))
        total = users_to_fix.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('All users already have capital assigned. Nothing to do.'))
            return

        women_count = 0
        other_count = 0

        for user in users_to_fix:
            if user.gender_identity == 'woman':
                user.individual_virtual_capital = Decimal('55000.00')
                women_count += 1
            else:
                user.individual_virtual_capital = Decimal('30000.00')
                other_count += 1
            user.save(update_fields=['individual_virtual_capital'])

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled {total} users: '
            f'{women_count} women (INR 55,000), '
            f'{other_count} others (INR 30,000)'
        ))
