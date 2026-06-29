from django.contrib import admin
from .models import Recipe, WeeklyPlan, DayAssignment


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display  = ['name', 'category', 'active_time_min',
                     'total_time_min', 'kcal', 'in_rotation',
                     'last_suggested', 'times_selected']
    list_filter   = ['category', 'in_rotation']
    list_editable = ['category', 'active_time_min']   # schnelle Korrektur
    search_fields = ['name']
    ordering      = ['name']


class DayAssignmentInline(admin.TabularInline):
    model = DayAssignment
    extra = 0


@admin.register(WeeklyPlan)
class WeeklyPlanAdmin(admin.ModelAdmin):
    list_display    = ['week_start', 'suggested_count',
                       'selected_count', 'created_at']
    filter_horizontal = ['suggested']        # bequeme Mehrfachauswahl
    readonly_fields = ['created_at']
    inlines         = [DayAssignmentInline]
    date_hierarchy  = 'week_start'

    @admin.display(description='Vorschläge')
    def suggested_count(self, obj):
        return obj.suggested.count()

    @admin.display(description='Gewählt')
    def selected_count(self, obj):
        return obj.assignments.count()


@admin.register(DayAssignment)
class DayAssignmentAdmin(admin.ModelAdmin):
    list_display = ['plan', 'day', 'recipe']
    list_filter  = ['day']
