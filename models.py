from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ArtistReport(db.Model):
    """Исходные данные отчета"""
    id = db.Column(db.Integer, primary_key=True)
    report_period = db.Column(db.String(50), nullable=False)  # Квартал/месяц
    usage_period = db.Column(db.String(50))  # Период использования
    platform = db.Column(db.String(100))  # Площадка
    territory = db.Column(db.String(50))  # Территория
    content_type = db.Column(db.String(50))  # Тип контента
    usage_type = db.Column(db.String(50))  # Вид использования
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    plays = db.Column(db.Integer, default=0)  # Количество прослушиваний
    revenue = db.Column(db.Float, default=0.0)  # Приход/доход
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Индекс для быстрого поиска по артисту и треку
    __table_args__ = (
        db.Index('idx_artist_track', 'artist', 'track_name'),
        db.Index('idx_period', 'report_period'),
    )

class TrackShare(db.Model):
    """Доля артиста в треке"""
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    share = db.Column(db.Float, default=100.0)  # Доля в процентах
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('artist', 'track_name', name='uq_artist_track'),
    )

class RoyaltySetting(db.Model):
    """Настройки процента вознаграждения"""
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    royalty_percent = db.Column(db.Float, default=50.0)  # % вознаграждения лицензиару
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('artist', 'track_name', name='uq_royalty_artist_track'),
    )

class TaxSetting(db.Model):
    """Настройки налогов"""
    id = db.Column(db.Integer, primary_key=True)
    tax_percent = db.Column(db.Float, default=6.0)  # Процент налога
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
