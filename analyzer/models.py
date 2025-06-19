from django.db import models


class Vacancy(models.Model):
    job_title = models.CharField(max_length=255)
    skills = models.TextField(blank=True)
    experience = models.CharField(max_length=10, choices=[
        ('0-1', '0-1 years'),
        ('1-3', '1-3 years'),
        ('3-5', '3-5 years'),
        ('5+', '5+ years')
    ])
    responsibilities = models.TextField(blank=True)
    level = models.CharField(max_length=20, choices=[
        ('junior', 'Junior'),
        ('middle', 'Middle'),
        ('senior', 'Senior')
    ])
    additional = models.TextField(blank=True)
    skills_priority = models.IntegerField(default=0)
    experience_priority = models.IntegerField(default=0)
    education_priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.job_title

    class Meta:
        verbose_name = 'Vacancy'
        verbose_name_plural = 'Vacancies'