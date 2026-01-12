from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, DateField, FileField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional
from flask_wtf.file import FileRequired, FileAllowed

class UploadForm(FlaskForm):
    period = StringField('Период отчета (например, Q1 2024)', 
                        validators=[DataRequired()])
    file = FileField('Файл отчета', 
                    validators=[
                        FileRequired(),
                        FileAllowed(['csv', 'xlsx', 'xls'], 'Только CSV и Excel файлы!')
                    ])

class TrackSettingsForm(FlaskForm):
    artist_share = FloatField('Доля артиста в треке (%)', 
                             validators=[DataRequired(), NumberRange(min=0, max=100)],
                             default=100.0)
    royalty_percent = FloatField('% Вознаграждения Лицензиару', 
                                validators=[DataRequired(), NumberRange(min=0, max=100)],
                                default=50.0)

class RoyaltyForm(FlaskForm):
    tracks = TextAreaField('Треки (формат: Артист - Название трека)',
                          validators=[DataRequired()],
                          description='Каждый трек с новой строки')
    royalty_percent = FloatField('Процент вознаграждения', 
                                validators=[DataRequired(), NumberRange(min=0, max=100)],
                                default=50.0)
