from flask import Flask, render_template, request, redirect, url_for, flash, make_response, Response
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
import chardet
import csv
import io
import re
from datetime import datetime
from werkzeug.utils import secure_filename
from collections import defaultdict

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music_reports.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Определяем модели
class ArtistReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_period = db.Column(db.String(50), nullable=False)
    usage_period = db.Column(db.String(50))
    platform = db.Column(db.String(100))
    territory = db.Column(db.String(50))
    content_type = db.Column(db.String(50))
    usage_type = db.Column(db.String(50))
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    plays = db.Column(db.Integer, default=0)
    revenue = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TrackShare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    share = db.Column(db.Float, default=100.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RoyaltySetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200), nullable=False)
    track_name = db.Column(db.String(300), nullable=False)
    royalty_percent = db.Column(db.Float, default=50.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Создаем таблицы
with app.app_context():
    db.create_all()

def detect_encoding(filepath):
    """Определяем кодировку файла"""
    with open(filepath, 'rb') as f:
        result = chardet.detect(f.read())
    return result['encoding']

def read_csv_with_encoding(filepath):
    """Читаем CSV файл с автоматическим определением кодировки"""
    encoding = detect_encoding(filepath)
    
    encodings_to_try = [encoding, 'utf-8', 'cp1251', 'windows-1251', 'latin1', 'iso-8859-1']
    
    for enc in encodings_to_try:
        try:
            df = pd.read_csv(filepath, encoding=enc)
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            continue
    
    try:
        df = pd.read_csv(filepath)
        return df
    except Exception as e:
        raise Exception(f"Не удалось прочитать файл. Ошибка: {str(e)}")

def calculate_track_values(track, apply_tax=False):
    """Расчет значений для одного трека"""
    track_share = TrackShare.query.filter_by(
        artist=track.artist,
        track_name=track.track_name
    ).first()
    
    royalty_setting = RoyaltySetting.query.filter_by(
        artist=track.artist,
        track_name=track.track_name
    ).first()
    
    artist_share = track_share.share if track_share else 100.0
    royalty_percent = royalty_setting.royalty_percent if royalty_setting else 50.0
    
    # Проверяем, есть ли настройки для трека
    has_settings = (track_share is not None) or (royalty_setting is not None)
    
    revenue = track.revenue
    
    if apply_tax:
        revenue = revenue * 0.94
    
    artist_revenue = revenue * (artist_share / 100.0)
    licensor_payment = artist_revenue * (royalty_percent / 100.0)
    
    return {
        'Доля артиста в треке (%)': artist_share,
        '% Вознаграждение Лицензиару': royalty_percent,
        'Вознаграждение Лицензиату': round(artist_revenue, 2),
        'К выплате Лицензиару за период': round(licensor_payment, 2),
        'Доход (после налога)' if apply_tax else 'Доход': round(revenue, 2),
        'has_settings': has_settings
    }

def safe_filename(filename):
    """Создает безопасное имя файла только с ASCII символами"""
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    return safe_name

def get_new_tracks_for_period(period):
    """Получает список новых треков за период (без настроек)"""
    # Получаем все треки за период
    period_tracks = ArtistReport.query.filter_by(report_period=period).all()
    
    # Получаем треки с настройками
    tracks_with_settings = set()
    for ts in TrackShare.query.all():
        tracks_with_settings.add(f"{ts.artist}||{ts.track_name}")
    for rs in RoyaltySetting.query.all():
        tracks_with_settings.add(f"{rs.artist}||{rs.track_name}")
    
    # Фильтруем новые треки
    new_tracks = []
    for track in period_tracks:
        track_key = f"{track.artist}||{track.track_name}"
        if track_key not in tracks_with_settings:
            new_tracks.append({
                'id': track.id,
                'artist': track.artist,
                'track_name': track.track_name,
                'platform': track.platform,
                'plays': track.plays
            })
    
    return new_tracks

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_report():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        period = request.form.get('period')
        
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        if file and period:
            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                if filename.endswith('.csv'):
                    df = read_csv_with_encoding(filepath)
                elif filename.endswith(('.xls', '.xlsx')):
                    df = pd.read_excel(filepath)
                else:
                    flash('Неподдерживаемый формат файла', 'error')
                    return redirect(request.url)
                
                column_mapping = {
                    'Период использования контента': 'usage_period',
                    'Площадка': 'platform',
                    'Территория': 'territory',
                    'Тип контента': 'content_type',
                    'Вид использования контента': 'usage_type',
                    'Исполнитель': 'artist',
                    'Название трека': 'track_name',
                    'Количество прослушиваний': 'plays',
                    'Доход': 'revenue',
                    'Revenue': 'revenue',
                    'Income': 'revenue',
                    'Стримы': 'plays',
                    'Прослушивания': 'plays',
                    'Streams': 'plays',
                    'Кол-во прослушиваний': 'plays'
                }
                
                for old_col in df.columns:
                    for key in column_mapping:
                        if key.lower() in old_col.lower():
                            df = df.rename(columns={old_col: column_mapping[key]})
                
                if 'revenue' not in df.columns:
                    df['revenue'] = df['plays'] * 0.01
                    flash('Колонка "Доход" не найдена. Рассчитана на основе количества прослушиваний.', 'info')
                
                records_added = 0
                for _, row in df.iterrows():
                    existing = ArtistReport.query.filter_by(
                        report_period=period,
                        artist=str(row.get('artist', '')),
                        track_name=str(row.get('track_name', '')),
                        platform=str(row.get('platform', ''))
                    ).first()
                    
                    if not existing:
                        try:
                            plays_value = float(row.get('plays', 0))
                            plays_value = int(plays_value)
                        except:
                            plays_value = 0
                        
                        try:
                            revenue_value = float(row.get('revenue', 0))
                        except:
                            revenue_value = 0.0
                        
                        report = ArtistReport(
                            report_period=period,
                            usage_period=str(row.get('usage_period', period)),
                            platform=str(row.get('platform', '')),
                            territory=str(row.get('territory', '')),
                            content_type=str(row.get('content_type', '')),
                            usage_type=str(row.get('usage_type', '')),
                            artist=str(row.get('artist', '')),
                            track_name=str(row.get('track_name', '')),
                            plays=plays_value,
                            revenue=revenue_value
                        )
                        db.session.add(report)
                        records_added += 1
                
                db.session.commit()
                flash(f'Отчет за период "{period}" успешно загружен. Добавлено {records_added} записей.', 'success')
                return redirect(url_for('view_reports'))
                
            except Exception as e:
                flash(f'Ошибка при обработке файла: {str(e)}', 'error')
                return redirect(request.url)
    
    return render_template('upload.html')

@app.route('/reports')
def view_reports():
    period = request.args.get('period', 'all')
    artist = request.args.get('artist', '')
    apply_tax = request.args.get('apply_tax', 'false') == 'true'
    only_new = request.args.get('only_new', 'false') == 'true'
    show_settings = request.args.get('show_settings', 'false') == 'true'
    
    query = ArtistReport.query
    
    if period and period != 'all':
        query = query.filter_by(report_period=period)
    
    if artist:
        query = query.filter(ArtistReport.artist.contains(artist))
    
    reports = query.order_by(ArtistReport.artist, ArtistReport.track_name).all()
    
    periods = ['all'] + [p[0] for p in db.session.query(ArtistReport.report_period).distinct().all() if p[0]]
    
    processed_reports = []
    for report in reports:
        calculations = calculate_track_values(report, apply_tax)
        processed_reports.append({
            'id': report.id,
            'report_period': report.report_period,
            'usage_period': report.usage_period,
            'platform': report.platform,
            'territory': report.territory,
            'content_type': report.content_type,
            'usage_type': report.usage_type,
            'artist': report.artist,
            'track_name': report.track_name,
            'plays': report.plays,
            'artist_share': calculations['Доля артиста в треке (%)'],
            'royalty_percent': calculations['% Вознаграждение Лицензиару'],
            'artist_revenue': calculations['Вознаграждение Лицензиату'],
            'licensor_payment': calculations['К выплате Лицензиару за период'],
            'revenue': calculations['Доход (после налога)' if apply_tax else 'Доход'],
            'has_settings': calculations['has_settings'],
            'is_new': not calculations['has_settings']
        })
    
    # Фильтруем только новые треки, если включен соответствующий фильтр
    if only_new:
        processed_reports = [r for r in processed_reports if r['is_new']]
    
    # Получаем список новых треков для текущего периода
    new_tracks_count = 0
    if period and period != 'all':
        new_tracks = get_new_tracks_for_period(period)
        new_tracks_count = len(new_tracks)
    
    artist_totals = {}
    total_revenue = 0
    total_artist_revenue = 0
    total_licensor_payment = 0
    
    for report in processed_reports:
        artist_name = report['artist']
        if artist_name not in artist_totals:
            artist_totals[artist_name] = {
                'total_licensor_payment': 0,
                'total_revenue': 0,
                'total_artist_revenue': 0,
                'track_count': 0,
                'new_tracks_count': 0
            }
        
        artist_totals[artist_name]['total_licensor_payment'] += report['licensor_payment']
        artist_totals[artist_name]['total_revenue'] += report['revenue']
        artist_totals[artist_name]['total_artist_revenue'] += report['artist_revenue']
        artist_totals[artist_name]['track_count'] += 1
        if report['is_new']:
            artist_totals[artist_name]['new_tracks_count'] += 1
        
        total_revenue += report['revenue']
        total_artist_revenue += report['artist_revenue']
        total_licensor_payment += report['licensor_payment']
    
    return render_template('reports.html', 
                         reports=processed_reports,
                         periods=periods,
                         apply_tax=apply_tax,
                         only_new=only_new,
                         show_settings=show_settings,
                         current_period=period,
                         current_artist=artist,
                         artist_totals=artist_totals,
                         total_revenue=round(total_revenue, 2),
                         total_artist_revenue=round(total_artist_revenue, 2),
                         total_licensor_payment=round(total_licensor_payment, 2),
                         new_tracks_count=new_tracks_count)

@app.route('/new_tracks/<period>')
def new_tracks_view(period):
    """Отдельная страница для просмотра только новых треков"""
    if not period or period == 'all':
        flash('Выберите конкретный период для просмотра новых треков', 'error')
        return redirect(url_for('view_reports'))
    
    new_tracks = get_new_tracks_for_period(period)
    
    return render_template('new_tracks.html',
                         period=period,
                         new_tracks=new_tracks,
                         tracks_count=len(new_tracks))

@app.route('/quick_settings/<int:track_id>', methods=['GET', 'POST'])
def quick_settings(track_id):
    """Быстрая настройка трека без перехода на отдельную страницу"""
    report = ArtistReport.query.get_or_404(track_id)
    
    if request.method == 'POST':
        try:
            artist_share = float(request.form.get('artist_share', 100))
            royalty_percent = float(request.form.get('royalty_percent', 50))
            
            track_share = TrackShare.query.filter_by(
                artist=report.artist,
                track_name=report.track_name
            ).first()
            
            if track_share:
                track_share.share = artist_share
            else:
                track_share = TrackShare(
                    artist=report.artist,
                    track_name=report.track_name,
                    share=artist_share
                )
                db.session.add(track_share)
            
            royalty_setting = RoyaltySetting.query.filter_by(
                artist=report.artist,
                track_name=report.track_name
            ).first()
            
            if royalty_setting:
                royalty_setting.royalty_percent = royalty_percent
            else:
                royalty_setting = RoyaltySetting(
                    artist=report.artist,
                    track_name=report.track_name,
                    royalty_percent=royalty_percent
                )
                db.session.add(royalty_setting)
            
            db.session.commit()
            
            # Возвращаем JSON для AJAX-запроса
            return jsonify({
                'success': True,
                'message': 'Настройки успешно сохранены',
                'artist_share': artist_share,
                'royalty_percent': royalty_percent
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Ошибка при сохранении настроек: {str(e)}'
            })
    
    # GET запрос - возвращаем текущие настройки
    track_share = TrackShare.query.filter_by(
        artist=report.artist,
        track_name=report.track_name
    ).first()
    
    royalty_setting = RoyaltySetting.query.filter_by(
        artist=report.artist,
        track_name=report.track_name
    ).first()
    
    return jsonify({
        'artist': report.artist,
        'track_name': report.track_name,
        'artist_share': track_share.share if track_share else 100.0,
        'royalty_percent': royalty_setting.royalty_percent if royalty_setting else 50.0,
        'has_settings': track_share is not None or royalty_setting is not None
    })

from flask import jsonify

@app.route('/bulk_quick_settings', methods=['POST'])
def bulk_quick_settings():
    """Массовая быстрая настройка для нескольких треков"""
    try:
        data = request.json
        track_ids = data.get('track_ids', [])
        artist_share = float(data.get('artist_share', 100))
        royalty_percent = float(data.get('royalty_percent', 50))
        
        if not track_ids:
            return jsonify({'success': False, 'message': 'Не выбраны треки'})
        
        updated_count = 0
        for track_id in track_ids:
            report = ArtistReport.query.get(track_id)
            if report:
                track_share = TrackShare.query.filter_by(
                    artist=report.artist,
                    track_name=report.track_name
                ).first()
                
                if track_share:
                    track_share.share = artist_share
                else:
                    track_share = TrackShare(
                        artist=report.artist,
                        track_name=report.track_name,
                        share=artist_share
                    )
                    db.session.add(track_share)
                
                royalty_setting = RoyaltySetting.query.filter_by(
                    artist=report.artist,
                    track_name=report.track_name
                ).first()
                
                if royalty_setting:
                    royalty_setting.royalty_percent = royalty_percent
                else:
                    royalty_setting = RoyaltySetting(
                        artist=report.artist,
                        track_name=report.track_name,
                        royalty_percent=royalty_percent
                    )
                    db.session.add(royalty_setting)
                
                updated_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Настройки применены для {updated_count} треков',
            'updated_count': updated_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Ошибка при сохранении настроек: {str(e)}'
        })

@app.route('/export')
def export_reports():
    period = request.args.get('period', '')
    artist = request.args.get('artist', '')
    apply_tax = request.args.get('apply_tax', 'false') == 'true'
    only_new = request.args.get('only_new', 'false') == 'true'
    
    if not period or period == 'all':
        flash('Выберите конкретный период для экспорта', 'error')
        return redirect(url_for('view_reports'))
    
    query = ArtistReport.query.filter_by(report_period=period)
    
    if artist:
        query = query.filter(ArtistReport.artist.contains(artist))
    
    reports = query.order_by(ArtistReport.artist, ArtistReport.track_name).all()
    
    if not reports:
        flash('Нет данных для выбранного периода', 'error')
        return redirect(url_for('view_reports'))
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    headers = [
        'Период использования контента',
        'Площадка',
        'Территория',
        'Тип контента',
        'Вид использования контента',
        'Исполнитель',
        'Название трека',
        'Количество прослушиваний',
        'Доля артиста в треке (%)',
        '% Вознаграждение Лицензиару',
        'Вознаграждение Лицензиату',
        'К выплате Лицензиару за период'
    ]
    
    if apply_tax:
        headers.append('Доход (после вычета 6% налога)')
    else:
        headers.append('Доход')
    
    writer.writerow(headers)
    
    artist_totals = defaultdict(float)
    total_licensor_payment = 0
    
    for report in reports:
        calculations = calculate_track_values(report, apply_tax)
        
        # Пропускаем треки с настройками, если включен фильтр "Только новые"
        if only_new and calculations['has_settings']:
            continue
        
        row = [
            report.usage_period or report.report_period,
            report.platform or '',
            report.territory or '',
            report.content_type or '',
            report.usage_type or '',
            report.artist,
            report.track_name,
            report.plays,
            calculations['Доля артиста в треке (%)'],
            calculations['% Вознаграждение Лицензиару'],
            calculations['Вознаграждение Лицензиату'],
            calculations['К выплате Лицензиару за период'],
            calculations['Доход (после налога)' if apply_tax else 'Доход']
        ]
        
        writer.writerow(row)
        
        artist_totals[report.artist] += calculations['К выплате Лицензиару за период']
        total_licensor_payment += calculations['К выплате Лицензиару за период']
    
    writer.writerow([])
    writer.writerow(['ИТОГИ ПО АРТИСТАМ'])
    writer.writerow(['Артист', 'Итоговая выплата'])
    
    for artist_name, total in sorted(artist_totals.items()):
        writer.writerow([artist_name, f"{total:.2f} ₽"])
    
    writer.writerow([])
    writer.writerow(['ОБЩИЙ ИТОГ', f"{total_licensor_payment:.2f} ₽"])
    
    writer.writerow([])
    writer.writerow(['Параметры экспорта:'])
    writer.writerow([f'Период: {period}'])
    if artist:
        writer.writerow([f'Артист: {artist}'])
    writer.writerow([f'Только новые треки: {"Да" if only_new else "Нет"}'])
    writer.writerow([f'Налог 6% вычтен: {"Да" if apply_tax else "Нет"}'])
    writer.writerow([f'Дата экспорта: {datetime.now().strftime("%d.%m.%Y %H:%M")}'])
    
    output.seek(0)
    response = make_response(output.getvalue().encode('utf-8-sig'))
    
    filename = f"music_report_{period}"
    if only_new:
        filename += "_new_tracks"
    if artist:
        artist_safe = safe_filename(artist)[:50]
        filename += f"_{artist_safe}"
    filename = safe_filename(filename) + ".csv"
    
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    
    return response

@app.route('/export_excel')
def export_excel():
    period = request.args.get('period', '')
    artist = request.args.get('artist', '')
    apply_tax = request.args.get('apply_tax', 'false') == 'true'
    only_new = request.args.get('only_new', 'false') == 'true'
    
    if not period or period == 'all':
        flash('Выберите конкретный период для экспорта', 'error')
        return redirect(url_for('view_reports'))
    
    query = ArtistReport.query.filter_by(report_period=period)
    
    if artist:
        query = query.filter(ArtistReport.artist.contains(artist))
    
    reports = query.order_by(ArtistReport.artist, ArtistReport.track_name).all()
    
    if not reports:
        flash('Нет данных для выбранного периода', 'error')
        return redirect(url_for('view_reports'))
    
    data = []
    artist_totals = defaultdict(float)
    total_licensor_payment = 0
    
    for report in reports:
        calculations = calculate_track_values(report, apply_tax)
        
        # Пропускаем треки с настройками, если включен фильтр "Только новые"
        if only_new and calculations['has_settings']:
            continue
        
        data.append({
            'Период использования контента': report.usage_period or report.report_period,
            'Площадка': report.platform or '',
            'Территория': report.territory or '',
            'Тип контента': report.content_type or '',
            'Вид использования контента': report.usage_type or '',
            'Исполнитель': report.artist,
            'Название трека': report.track_name,
            'Количество прослушиваний': report.plays,
            'Доля артиста в треке (%)': calculations['Доля артиста в треке (%)'],
            '% Вознаграждение Лицензиару': calculations['% Вознаграждение Лицензиару'],
            'Вознаграждение Лицензиату': calculations['Вознаграждение Лицензиату'],
            'К выплате Лицензиару за период': calculations['К выплате Лицензиару за период'],
            'Доход (после налога)' if apply_tax else 'Доход': calculations['Доход (после налога)' if apply_tax else 'Доход']
        })
        
        artist_totals[report.artist] += calculations['К выплате Лицензиару за период']
        total_licensor_payment += calculations['К выплате Лицензиару за период']
    
    if not data:
        flash('Нет данных для экспорта с выбранными фильтрами', 'error')
        return redirect(url_for('view_reports'))
    
    df_data = pd.DataFrame(data)
    
    totals_data = []
    for artist_name, total in sorted(artist_totals.items()):
        totals_data.append({
            'Артист': artist_name,
            'Итоговая выплата': f"{total:.2f} ₽"
        })
    
    totals_data.append({
        'Артист': 'ОБЩИЙ ИТОГ',
        'Итоговая выплата': f"{total_licensor_payment:.2f} ₽"
    })
    
    df_totals = pd.DataFrame(totals_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_data.to_excel(writer, index=False, sheet_name='Данные')
        df_totals.to_excel(writer, index=False, sheet_name='Итоги')
        
        worksheet_data = writer.sheets['Данные']
        for column in worksheet_data.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet_data.column_dimensions[column_letter].width = adjusted_width
        
        worksheet_totals = writer.sheets['Итоги']
        worksheet_totals.column_dimensions['A'].width = 40
        worksheet_totals.column_dimensions['B'].width = 20
        
        info_data = {
            'Параметр': ['Период', 'Артист', 'Только новые треки', 'Налог 6% вычтен', 'Дата экспорта'],
            'Значение': [
                period,
                artist if artist else 'Все артисты',
                'Да' if only_new else 'Нет',
                'Да' if apply_tax else 'Нет',
                datetime.now().strftime("%d.%m.%Y %H:%M")
            ]
        }
        df_info = pd.DataFrame(info_data)
        df_info.to_excel(writer, index=False, sheet_name='Инфо')
        
        worksheet_info = writer.sheets['Инфо']
        worksheet_info.column_dimensions['A'].width = 20
        worksheet_info.column_dimensions['B'].width = 30
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    
    filename = f"music_report_{period}"
    if only_new:
        filename += "_new_tracks"
    if artist:
        artist_safe = safe_filename(artist)[:50]
        filename += f"_{artist_safe}"
    filename = safe_filename(filename) + ".xlsx"
    
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    return response

@app.route('/export_artist/<artist_name>')
def export_artist(artist_name):
    """Экспорт отчета по конкретному артисту"""
    try:
        period = request.args.get('period', '')
        apply_tax = request.args.get('apply_tax', 'false') == 'true'
        only_new = request.args.get('only_new', 'false') == 'true'
        
        query = ArtistReport.query.filter(ArtistReport.artist == artist_name)
        
        if period and period != 'all' and period != '':
            query = query.filter_by(report_period=period)
        
        reports = query.order_by(ArtistReport.report_period, ArtistReport.track_name).all()
        
        if not reports:
            flash(f'Нет данных для артиста {artist_name}', 'warning')
            return redirect(url_for('view_reports'))
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        
        headers = [
            'Период отчета',
            'Период использования',
            'Площадка',
            'Территория',
            'Тип контента',
            'Вид использования',
            'Исполнитель',
            'Название трека',
            'Количество прослушиваний',
            'Доля артиста в треке (%)',
            '% Вознаграждение Лицензиару',
            'Вознаграждение Лицензиату',
            'К выплате Лицензиару за период',
            'Доход' + (' (после вычета 6% налога)' if apply_tax else '')
        ]
        
        writer.writerow(headers)
        
        total_licensor_payment = 0
        
        for report in reports:
            calculations = calculate_track_values(report, apply_tax)
            
            # Пропускаем треки с настройками, если включен фильтр "Только новые"
            if only_new and calculations['has_settings']:
                continue
            
            row = [
                report.report_period,
                report.usage_period or report.report_period,
                report.platform or '',
                report.territory or '',
                report.content_type or '',
                report.usage_type or '',
                report.artist,
                report.track_name,
                report.plays,
                calculations['Доля артиста в треке (%)'],
                calculations['% Вознаграждение Лицензиару'],
                calculations['Вознаграждение Лицензиату'],
                calculations['К выплате Лицензиару за период'],
                calculations['Доход (после налога)' if apply_tax else 'Доход']
            ]
            
            writer.writerow(row)
            total_licensor_payment += calculations['К выплате Лицензиару за период']
        
        writer.writerow([])
        writer.writerow(['ИТОГ ДЛЯ АРТИСТА', '', '', '', '', '', artist_name, '', '', '', '', '', f"{total_licensor_payment:.2f} ₽"])
        
        output.seek(0)
        csv_data = output.getvalue()
        
        filename = f"report_{artist_name}"
        if period and period != 'all' and period != '':
            filename += f"_{period}"
        if only_new:
            filename += "_new_tracks"
        filename = safe_filename(filename) + ".csv"
        
        response = Response(
            csv_data.encode('utf-8-sig'),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Ошибка при экспорте: {str(e)}', 'error')
        return redirect(url_for('view_reports'))

@app.route('/settings/track/<int:track_id>', methods=['GET', 'POST'])
def track_settings(track_id):
    report = ArtistReport.query.get_or_404(track_id)
    
    if request.method == 'POST':
        try:
            artist_share = float(request.form.get('artist_share', 100))
            royalty_percent = float(request.form.get('royalty_percent', 50))
            
            track_share = TrackShare.query.filter_by(
                artist=report.artist,
                track_name=report.track_name
            ).first()
            
            if track_share:
                track_share.share = artist_share
            else:
                track_share = TrackShare(
                    artist=report.artist,
                    track_name=report.track_name,
                    share=artist_share
                )
                db.session.add(track_share)
            
            royalty_setting = RoyaltySetting.query.filter_by(
                artist=report.artist,
                track_name=report.track_name
            ).first()
            
            if royalty_setting:
                royalty_setting.royalty_percent = royalty_percent
            else:
                royalty_setting = RoyaltySetting(
                    artist=report.artist,
                    track_name=report.track_name,
                    royalty_percent=royalty_percent
                )
                db.session.add(royalty_setting)
            
            db.session.commit()
            flash('Настройки трека успешно сохранены', 'success')
            return redirect(url_for('view_reports'))
            
        except Exception as e:
            flash(f'Ошибка при сохранении настроек: {str(e)}', 'error')
    
    return render_template('track_settings.html', report=report)

@app.route('/settings')
def settings():
    return redirect(url_for('bulk_settings'))

@app.route('/settings/bulk', methods=['GET', 'POST'])
def bulk_settings():
    if request.method == 'POST':
        tracks_text = request.form.get('tracks', '')
        royalty_percent = request.form.get('royalty_percent', '50')
        
        if not tracks_text or not royalty_percent:
            flash('Заполните все поля', 'error')
            return redirect(url_for('bulk_settings'))
        
        try:
            royalty_percent_float = float(royalty_percent)
            if not 0 <= royalty_percent_float <= 100:
                flash('Процент должен быть от 0 до 100', 'error')
                return redirect(url_for('bulk_settings'))
        except ValueError:
            flash('Процент должен быть числом', 'error')
            return redirect(url_for('bulk_settings'))
        
        tracks_list = [t.strip() for t in tracks_text.split('\n') if t.strip()]
        updated_count = 0
        
        for track_line in tracks_list:
            if ' - ' in track_line:
                parts = track_line.split(' - ', 1)
                artist = parts[0].strip()
                track_name = parts[1].strip()
                
                report_exists = ArtistReport.query.filter_by(
                    artist=artist,
                    track_name=track_name
                ).first()
                
                if report_exists:
                    royalty_setting = RoyaltySetting.query.filter_by(
                        artist=artist,
                        track_name=track_name
                    ).first()
                    
                    if royalty_setting:
                        royalty_setting.royalty_percent = royalty_percent_float
                    else:
                        royalty_setting = RoyaltySetting(
                            artist=artist,
                            track_name=track_name,
                            royalty_percent=royalty_percent_float
                        )
                        db.session.add(royalty_setting)
                    
                    updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            flash(f'Настройки применены для {updated_count} треков', 'success')
        else:
            flash('Не найдено треков для применения настроек', 'warning')
        
        return redirect(url_for('bulk_settings'))
    
    royalty_settings = RoyaltySetting.query.order_by(RoyaltySetting.artist, RoyaltySetting.track_name).all()
    track_shares = TrackShare.query.order_by(TrackShare.artist, TrackShare.track_name).all()
    
    return render_template('edit_settings.html', 
                         royalty_settings=royalty_settings,
                         track_shares=track_shares)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')