from django.db import models


class Recipe(models.Model):
    CATEGORY_CHOICES = [
        ('meat',   'Fleisch'),
        ('fish',   'Fisch'),
        ('veggie', 'Vegetarisch'),
    ]
    cookidoo_id     = models.CharField(max_length=100, unique=True)
    name            = models.CharField(max_length=200)
    active_time_min = models.IntegerField()
    total_time_min  = models.IntegerField()
    category        = models.CharField(max_length=10, choices=CATEGORY_CHOICES,
                                       default='veggie')
    kcal            = models.IntegerField(null=True, blank=True)
    protein_g       = models.IntegerField(null=True, blank=True)
    url             = models.URLField(blank=True)
    in_rotation     = models.BooleanField(default=True)
    last_suggested  = models.DateField(null=True, blank=True)
    last_selected   = models.DateField(null=True, blank=True)
    times_selected  = models.IntegerField(default=0)
    is_candidate = models.BooleanField(default=False)

    def __str__(self):
        tag = {'meat': '🍖', 'fish': '🐟', 'veggie': '🌿'}[self.category]
        return f"{tag} {self.name} ({self.active_time_min} min)"

class WeeklyPlan(models.Model):
    week_start    = models.DateField(unique=True)
    suggested     = models.ManyToManyField(Recipe, related_name='suggested_in',
                                           blank=True)
    selected = models.ManyToManyField(Recipe, related_name='selected_in', blank=True)
    feedback_text = models.TextField(blank=True)
    reasoning     = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    awaiting_feedback = models.BooleanField(default=False)

    def __str__(self):
        return f"Woche ab {self.week_start}"

class DayAssignment(models.Model):
    DAYS = [('Mo', 'Montag'), ('Mi', 'Mittwoch'), ('Do', 'Donnerstag'),
            ('Fr', 'Freitag'), ('Sa', 'Samstag'), ('So', 'Sonntag')]
    plan   = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE,
                               related_name='assignments')
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE)
    day    = models.CharField(max_length=2, choices=DAYS)

    class Meta:
        unique_together = ('plan', 'day')