import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, date
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# -------------------- AYARLAR --------------------
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"  # Colab'da environment variable yerine direkt
CHAT_ID = "YOUR_CHAT_ID"

# Trading Ayarları
PORTFOLIO_SIZE = 50_000  # USD (Colab için daha küçük)
RISK_PER_TRADE = 0.01    # %1 risk
MAX_POSITIONS = 3        # Colab için daha az pozisyon
SUPER_TREND_PERIOD = 10
SUPER_TREND_MULT = 3.0
ATR_PERIOD = 14
MAX_PULLBACK_ATR = 2.0

# -------------------- OPTIMIZE HİSSE LİSTESİ --------------------
def get_optimized_tickers():
    """Sadece likit ve büyük cap hisseler"""
    premium_tickers = [
        # Teknoloji
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'ADBE', 'NFLX',
        # Finans
        'JPM', 'V', 'MA', 'BAC', 'WFC',
        # Sağlık
        'JNJ', 'PFE', 'UNH', 'MRK', 'ABBV',
        # Tüketim
        'PG', 'KO', 'PEP', 'WMT', 'COST',
        # Endüstriyel
        'CAT', 'BA', 'MMM', 'HON',
        # Enerji
        'XOM', 'CVX',
        # İletişim
        'T', 'VZ', 'CMCSA',
        # Sektör ETF'leri (trend kontrolü için)
        'SPY', 'QQQ', 'DIA'
    ]
    return premium_tickers

# -------------------- VERİ DOĞRULAMA --------------------
def validate_data(df, symbol):
    """Veri kalitesi kontrolü"""
    if df is None or len(df) < 50:
        logging.warning(f"{symbol}: Yetersiz veri")
        return False
    
    # Volume kontrolü (en son 10 hafta ortalaması)
    if 'Volume' in df.columns:
        avg_volume = df['Volume'].tail(10).mean()
        if avg_volume < 1000000:  # 1M hacim filtresi
            logging.warning(f"{symbol}: Düşük hacim ({avg_volume:,.0f})")
            return False
    
    # Eksik veri kontrolü
    if df.isnull().any().any():
        logging.warning(f"{symbol}: Eksik veri var")
        return False
    
    # Son veri güncelliği
    last_date = df.index[-1]
    days_since_update = (datetime.now().date() - last_date.date()).days
    if days_since_update > 14:
        logging.warning(f"{symbol}: Güncel olmayan veri ({days_since_update} gün)")
        return False
    
    return True

# -------------------- GELİŞMİŞ SUPER TREND --------------------
def calculate_supertrend(df):
    """SuperTrend + ATR + R-Score hesaplama"""
    try:
        # SuperTrend
        st = ta.trend.SuperTrendIndicator(
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'],
            period=SUPER_TREND_PERIOD,
            multiplier=SUPER_TREND_MULT
        )
        df['SuperTrend'] = st.supertrend()
        df['SuperTrend_Direction'] = st.supertrend_trend()
        
        # ATR
        df['ATR'] = ta.volatility.AverageTrueRange(
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'], 
            window=ATR_PERIOD
        ).average_true_range()
        
        # R-Score geliştirilmiş
        trend_strength = (df['SuperTrend_Direction'] == 1).rolling(10).mean().iloc[-1]
        
        # Pullback score: SuperTrend'a ne kadar yakın
        current_price = df['Close'].iloc[-1]
        current_st = df['SuperTrend'].iloc[-1]
        distance_ratio = (current_price - current_st) / current_st
        pullback_score = max(0, 1 - abs(distance_ratio) / 0.1)  # %10'den fazla uzaklaşmada düşük score
        
        # Momentum score
        price_above_ma = (current_price > df['Close'].rolling(20).mean().iloc[-1])
        momentum_score = 1 if price_above_ma else 0.3
        
        df['R_Score'] = (trend_strength * 0.4 + 
                        pullback_score * 0.4 + 
                        momentum_score * 0.2)
        
        return df
        
    except Exception as e:
        logging.error(f"SuperTrend hesaplama hatası: {e}")
        return None

# -------------------- PARALEL HİSSE ANALİZİ --------------------
def analyze_single_stock(ticker):
    """Tek hisse analizi - paralel işlem için"""
    try:
        # Haftalık veri çek (2 yıl yeterli)
        df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        
        if not validate_data(df, ticker):
            return None
        
        # Teknik analiz
        df = calculate_supertrend(df)
        if df is None:
            return None
            
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ALIM KOŞULLARI
        # 1. Yukarı trend
        if current['SuperTrend_Direction'] != 1:
            return None
            
        # 2. Fiyat SuperTrend üstünde
        if current['Close'] <= current['SuperTrend']:
            return None
            
        # 3. Pullback kontrolü
        pullback_distance = current['Close'] - current['SuperTrend']
        if pullback_distance > (MAX_PULLBACK_ATR * current['ATR']):
            return None
            
        # 4. Stop loss ve risk hesaplama
        stop_price = current['SuperTrend']
        risk_per_share = current['Close'] - stop_price
        
        if risk_per_share <= 0:
            return None
            
        # Pozisyon büyüklüğü
        max_risk_usd = PORTFOLIO_SIZE * RISK_PER_TRADE
        shares = max_risk_usd / risk_per_share
        shares = int(shares)  # Tam sayı hisse
        
        if shares < 1:
            return None
            
        position_value = shares * current['Close']
        actual_risk = shares * risk_per_share
        
        return {
            'ticker': ticker,
            'price': current['Close'],
            'stop': stop_price,
            'shares': shares,
            'position_value': position_value,
            'actual_risk': actual_risk,
            'r_score': current['R_Score'],
            'atr_ratio': pullback_distance / current['ATR'],
            'risk_reward': (current['Close'] - stop_price) / stop_price
        }
        
    except Exception as e:
        logging.error(f"{ticker} analiz hatası: {e}")
        return None

# -------------------- PİYASA DURUMU KONTROLÜ --------------------
def check_market_condition():
    """Genel piyasa trendi kontrolü"""
    try:
        spy_data = yf.download('SPY', period='6mo', interval='1wk', progress=False)
        if len(spy_data) < 10:
            return True  # Güvenli mod
            
        # SPY 50 günlük MA üstünde mi?
        spy_data['MA50'] = spy_data['Close'].rolling(10).mean()  # 10 hafta ≈ 50 gün
        current_spy = spy_data.iloc[-1]
        
        if current_spy['Close'] > current_spy['MA50']:
            return True  # Bullish market
        else:
            logging.warning("Piyasa koşulları uygun değil (SPY < MA50)")
            return False
            
    except Exception as e:
        logging.error(f"Piyasa kontrol hatası: {e}")
        return True  # Hata durumunda devam et

# -------------------- TELEGRAM BİLDİRİMİ --------------------
def send_telegram_message(message):
    """Telegram'a mesaj gönder"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"Telegram gönderim hatası: {e}")
        return False

# -------------------- ANA TARAMA FONKSİYONU --------------------
def run_weekly_scan():
    """Ana tarama fonksiyonu - Colab için optimize"""
    
    print("🔍 Haftalık tarama başlatılıyor...")
    
    # Piyasa kontrolü
    if not check_market_condition():
        message = "🚫 *PİYASA UYARI*: SPY 50 günlük MA altında. Bu hafta tarama atlanıyor."
        send_telegram_message(message)
        print(message)
        return
    
    # Hisse listesi
    tickers = get_optimized_tickers()
    print(f"📊 {len(tickers)} hisse analiz ediliyor...")
    
    # Paralel analiz
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(analyze_single_stock, ticker): ticker for ticker in tickers}
        
        for future in as_completed(future_to_ticker):
            result = future.result()
            if result:
                candidates.append(result)
    
    # Sırala ve filtrele
    candidates.sort(key=lambda x: x['r_score'], reverse=True)
    best_candidates = candidates[:MAX_POSITIONS]
    
    # Rapor oluştur
    if best_candidates:
        total_risk = sum(c['actual_risk'] for c in best_candidates)
        total_investment = sum(c['position_value'] for c in best_candidates)
        
        message = f"🎯 *HAFTALIK ALIM SİNYALLERİ* ({date.today().strftime('%d.%m.%Y')})\n\n"
        message += f"Portföy: ${PORTFOLIO_SIZE:,} | Risk: %{RISK_PER_TRADE*100}\n"
        message += f"Toplam Yatırım: ${total_investment:,.0f}\n"
        message += f"Toplam Risk: ${total_risk:,.0f} (%{total_risk/PORTFOLIO_SIZE:.1f})\n\n"
        
        for candidate in best_candidates:
            message += (
                f"✅ *{candidate['ticker']}*\n"
                f"Fiyat: ${candidate['price']:.2f} | Stop: ${candidate['stop']:.2f}\n"
                f"Hisse: {candidate['shares']:,} | Pozisyon: ${candidate['position_value']:,.0f}\n"
                f"Risk: ${candidate['actual_risk']:,.0f} | R-Score: {candidate['r_score']:.2f}\n\n"
            )
    else:
        message = f"📭 *SONUÇ*: {date.today().strftime('%d.%m.%Y')} tarihi için uygun alım sinyali bulunamadı.\n\n"
        message += "Nakitte kalmak en güvenli seçenek olabilir."
    
    message += "\n---\n"
    message += "⚠️ _Eğitim amaçlıdır. Yatırım tavsiyesi değildir._"
    
    # Gönder
    if send_telegram_message(message):
        print("✅ Telegram bildirimi gönderildi")
    else:
        print("❌ Telegram gönderilemedi")
    
    print(f"📈 {len(best_candidates)} sinyal bulundu")
    return best_candidates

# -------------------- COLAB TEST FONKSİYONU --------------------
def test_single_stock(ticker="AAPL"):
    """Tek hisse testi - Colab'da hızlı kontrol"""
    print(f"🧪 Test analizi: {ticker}")
    result = analyze_single_stock(ticker)
    
    if result:
        print(f"✅ Sinyal var: {result}")
    else:
        print(f"❌ Sinyal yok: {ticker}")
    
    return result

# -------------------- ÇALIŞTIRMA --------------------
if __name__ == "__main__":
    # Colab'da çalıştırılacak kısım
    print("🚀 S&P 500 SuperTrend Scanner - Colab Optimize")
    print("=" * 50)
    
    # Hızlı test
    test_single_stock("AAPL")
    test_single_stock("MSFT")
    
    print("\n" + "=" * 50)
    
    # Tam tarama (isteğe bağlı - zaman alır)
    run_full_scan = False  # True yaparak tam taramayı aç
    
    if run_full_scan:
        signals = run_weekly_scan()
        if signals:
            print(f"🎉 Tarama tamamlandı: {len(signals)} sinyal")
        else:
            print("ℹ️ Sinyal bulunamadı")
    else:
        print("ℹ️ Tam tarama kapalı. 'run_full_scan = True' yaparak açabilirsiniz.")
