import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, date
import logging
from import yfinance as yf
import pandas as pd
import numpy as np
import requests # Yeni eklenen kütüphane

# --- TELEGRAM SABİTLERİ (Lütfen Kendi Bilgilerinizle Değiştirin) ---
# Botunuzdan aldığınız token. (Örn: '123456789:ABC-DEF123456...')
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" 
# Mesajı göndermek istediğiniz chat ID'si. (Örn: '-1001234567890' veya '@kullanici_adiniz')
CHAT_ID = "YOUR_CHAT_ID" 
# -------------------------------------------------------------------

# Finansal sabitler ve parametreler
AGRESİF_PİYASA_DEĞERİ_MAKS = 500_000_000 # $500 Milyon
DENGELİ_PİYASA_DEĞERİ_MİN = 10_000_000_000 # $10 Milyar

class DualStrategyScreener:
    """
    Belirtilen 'AGRESİF' ve 'DENGELİ' stratejilere göre ABD borsası 
    için hisse taraması ve öneri sunan modüler sınıf. Telegram entegrasyonu eklenmiştir.
    """
    def __init__(self, tickers, strategy, telegram_token, chat_id):
        self.tickers = tickers
        self.strategy = strategy.upper()
        self.raw_data = {}
        self.fundamentals = {}
        self.analysis_results = pd.DataFrame()
        self.telegram_token = telegram_token
        self.chat_id = chat_id

        if self.strategy not in ['AGRESİF', 'DENGELİ']:
            raise ValueError("Strateji 'AGRESİF' veya 'DENGELİ' olmalıdır.")
        
        print(f"✅ Strateji Seçildi: **{self.strategy}**")
        
    # --- 1. Veri Çekme Modülü (Data Retrieval Module) ---
    # (Önceki kod ile aynı)
    def fetch_data(self):
        """
        yfinance kullanarak fiyat/hacim ve temel verileri çeker.
        """
        print("⏳ Veri Çekme Başlatılıyor...")
        
        if self.strategy == 'AGRESİF':
            period = '30d' 
        else:
            period = '1y' 

        for ticker in self.tickers:
            try:
                hist = yf.download(ticker, period=period, interval='1d', progress=False)
                info = yf.Ticker(ticker).info
                
                if not hist.empty and info:
                    self.raw_data[ticker] = hist
                    self.fundamentals[ticker] = info
                else:
                    print(f"⚠️ {ticker} için veri bulunamadı veya eksik.")
                    
            except Exception as e:
                print(f"❌ {ticker} veri çekme hatası: {e}")
        
        print(f"✅ {len(self.raw_data)} hisse için veri çekimi tamamlandı.")
        
    # --- 2. Filtreleme Modülü (Filtering Module) ---
    # (Önceki kod ile aynı)
    def filter_by_market_cap_and_fundamentals(self):
        """
        Seçilen stratejiye göre piyasa değeri ve temel kriterlere göre filtreleme yapar.
        """
        print("⏳ Hisse Listesi Filtreleme Başlatılıyor...")
        
        filtered_tickers = []
        
        for ticker, info in self.fundamentals.items():
            market_cap = info.get('marketCap')
            
            if market_cap is None:
                continue

            if self.strategy == 'AGRESİF':
                if market_cap <= AGRESİF_PİYASA_DEĞERİ_MAKS:
                    filtered_tickers.append(ticker)
                    
            elif self.strategy == 'DENGELİ':
                if market_cap >= DENGELİ_PİYASA_DEĞERİ_MİN:
                    revenue_growth = info.get('revenueGrowth', 0.0) 
                    if revenue_growth > 0.10: 
                        filtered_tickers.append(ticker)
                        
        print(f"✅ {len(filtered_tickers)} hisse filtrelemeden geçti.")
        self.tickers = filtered_tickers
        
    # --- 3. Analiz Modülü (Analysis Module) ---
    # (Önceki kod ile aynı, MACD ve RSI hesaplama dahil)
    def calculate_indicators_and_score(self):
        """
        Her hisse için teknik/temel indikatörleri hesaplar ve skor verir.
        """
        print("⏳ Teknik ve Temel Analizler Başlatılıyor...")
        
        results = []
        
        for ticker in self.tickers:
            data = self.raw_data.get(ticker)
            info = self.fundamentals.get(ticker)
            
            if data is None or info is None:
                continue
            
            score = 0
            justification = []
            
            if self.strategy == 'AGRESİF':
                # --------------------- AGRESİF KRİTERLER ---------------------
                
                # 1. Hacim Artışı
                avg_volume_20d = data['Volume'].iloc[-21:-1].mean()
                current_volume = data['Volume'].iloc[-1]
                volume_ratio = current_volume / avg_volume_20d
                
                if volume_ratio >= 3.0:
                    score += 4
                    justification.append(f"Hacim Artışı: %{round(volume_ratio * 100)} (Katalizör Sinyali)")
                    
                # 2. MACD Al Sinyali
                data['EMA12'] = data['Close'].ewm(span=12, adjust=False).mean()
                data['EMA26'] = data['Close'].ewm(span=26, adjust=False).mean()
                data['MACD'] = data['EMA12'] - data['EMA26']
                data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()

                if (data['MACD'].iloc[-2] < data['Signal_Line'].iloc[-2]) and \
                   (data['MACD'].iloc[-1] > data['Signal_Line'].iloc[-1]):
                    score += 3
                    justification.append("MACD Hattı, Sinyal Hattını Yukarı Kesti (Momentum Sinyali)")

                # 3. RSI (7 Günlük) Geri Dönüş
                data['RSI_7'] = self._calculate_rsi(data['Close'], window=7)
                rsi_prev = data['RSI_7'].iloc[-2]
                rsi_current = data['RSI_7'].iloc[-1]
                
                if (30 <= rsi_prev <= 40) and (rsi_current > rsi_prev):
                    score += 3
                    justification.append(f"RSI(7) {round(rsi_prev)}-{round(rsi_current)} aralığından yukarı döndü (Tepki Sinyali)")
                    
            elif self.strategy == 'DENGELİ':
                # --------------------- DENGELİ KRİTERLER ---------------------
                
                # 1. Gelir/Kâr Büyümesi
                revenue_growth = info.get('revenueGrowth', 0.0) 
                if revenue_growth > 0.10:
                    score += 3
                    justification.append(f"Yıllık Gelir Büyümesi: %{round(revenue_growth * 100)} > %10")
                    
                # 2. Debt/Equity
                debt_to_equity = info.get('debtToEquity')
                if debt_to_equity is not None and debt_to_equity < 0.5:
                    score += 2
                    justification.append(f"D/E Oranı: {round(debt_to_equity, 2)} (Düşük Borçluluk)")
                    
                # 3. ROE/ROI
                return_on_equity = info.get('returnOnEquity')
                if return_on_equity is not None and return_on_equity > 0.15:
                    score += 2
                    justification.append(f"ROE: %{round(return_on_equity * 100)} (Yüksek Karlılık)")
                
                # 4. 200 Günlük MA
                data['MA_200'] = data['Close'].rolling(window=200).mean()
                
                if data['Close'].iloc[-1] > data['MA_200'].iloc[-1]:
                    score += 3
                    justification.append("Fiyat, 200 Günlük Ortalamanın Üzerinde (Uzun Vadeli Trend)")

                # 5. RSI (14 Günlük) Sağlıklı Trend
                data['RSI_14'] = self._calculate_rsi(data['Close'], window=14)
                rsi_current = data['RSI_14'].iloc[-1]
                
                if 40 <= rsi_current <= 65:
                    score += 2
                    justification.append(f"RSI(14): {round(rsi_current, 1)} (Sağlıklı Trend)")

            entry_price = data['Close'].iloc[-1]
            
            results.append({
                'Hisse': ticker,
                'Skor': score,
                'Gerekçe': " | ".join(justification),
                'Son Kapanış': entry_price,
                'RSI_Son': data.get('RSI_7', data.get('RSI_14', np.nan)).iloc[-1]
            })

        self.analysis_results = pd.DataFrame(results)
        self.analysis_results = self.analysis_results[self.analysis_results['Skor'] > 0]
        
        if self.analysis_results.empty:
            print("❌ Analiz kriterlerine uyan hisse bulunamadı.")
            return

        print(f"✅ Analiz tamamlandı. {len(self.analysis_results)} hisse skor aldı.")

    # RSI Hesaplama Yardımcı Fonksiyonu
    def _calculate_rsi(self, series, window):
        diff = series.diff(1).dropna()
        gain = (diff.where(diff > 0, 0)).rolling(window=window).mean()
        loss = (-diff.where(diff < 0, 0)).rolling(window=window).mean()
        RS = gain / loss
        return 100 - (100 / (1 + RS))
    
    # --- 4. Risk Yönetimi Modülü (Risk Management Module) ---
    # (Önceki kod ile aynı)
    def calculate_risk_levels(self):
        """
        Giriş fiyatına göre Stop-Loss ve Hedef Fiyat seviyelerini hesaplar.
        """
        if self.analysis_results.empty:
            return

        print("⏳ Risk Yönetimi Seviyeleri Hesaplanıyor...")
        
        if self.strategy == 'AGRESİF':
            stop_loss_pct = 0.05
            target_pct = 0.15
        else:
            stop_loss_pct = 0.10
            target_pct = 0.30 
            
        self.analysis_results['Stop-Loss (%)'] = -stop_loss_pct * 100
        self.analysis_results['Hedef Fiyat (%)'] = target_pct * 100
        
        self.analysis_results['Stop-Loss Fiyatı'] = \
            self.analysis_results['Son Kapanış'] * (1 - stop_loss_pct)
            
        self.analysis_results['Hedef Fiyatı'] = \
            self.analysis_results['Son Kapanış'] * (1 + target_pct)

        cols_to_round = ['Son Kapanış', 'Stop-Loss Fiyatı', 'Hedef Fiyatı', 'RSI_Son']
        self.analysis_results[cols_to_round] = self.analysis_results[cols_to_round].round(2)
        
        print("✅ Risk seviyeleri hesaplandı.")

    # --- 5. Raporlama Modülü (Reporting Module) ---
    # (Önceki kod ile aynı)
    def generate_report(self, top_n=5):
        """
        En yüksek skorlu hisseleri içeren temiz bir DataFrame döndürür.
        """
        if self.analysis_results.empty:
            return "Analiz kriterlerine uyan hisse bulunamadı.", None
        
        report = self.analysis_results.sort_values(by='Skor', ascending=False).head(top_n)
        
        final_report = report[['Hisse', 'Skor', 'Gerekçe', 'Son Kapanış', 'Stop-Loss Fiyatı', 'Hedef Fiyatı', 'Stop-Loss (%)', 'Hedef Fiyat (%)']]
        
        title = f"🌟 En İyi {top_n} Hisse Önerisi ({self.strategy} Stratejisi)"
        
        return title, final_report
        
    # --- 6. Telegram Raporlama Modülü (Telegram Reporting Module) ---
    def send_telegram_message(self, title, report_df):
        """
        Analiz sonuçlarını Telegram'a Markdown formatında gönderir.
        """
        if report_df is None or report_df.empty:
            message = f"🚨 {title}\nAnaliz kriterlerine uyan hisse bulunamadı."
        else:
            # Markdown tablosu oluşturma
            table_markdown = report_df.to_markdown(index=False)
            
            message = (
                f"**{title}**\n\n"
                f"Tarih: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"```{table_markdown}```\n\n"
                f"*Not: Fiyatlar $USD cinsindendir. Sadece eğitim amaçlıdır.*"
            )

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status() # HTTP hatalarını yakala
            print("✅ Telegram mesajı başarıyla gönderildi.")
        except requests.exceptions.HTTPError as err:
            print(f"❌ Telegram API Hatası: {err}")
            print("Lütfen TELEGRAM_TOKEN ve CHAT_ID ayarlarınızı kontrol edin.")
        except Exception as e:
            print(f"❌ Telegram Gönderme Hatası: {e}")

    # Ana Çalıştırıcı Fonksiyon (Güncellendi)
    def run_screener(self):
        """Tüm modülleri sırayla çalıştırır ve Telegram'a rapor gönderir."""
        self.fetch_data()
        self.filter_by_market_cap_and_fundamentals()
        self.calculate_indicators_and_score()
        self.calculate_risk_levels()
        
        title, report_df = self.generate_report()
        
        # Telegram'a rapor gönderme adımı
        self.send_telegram_message(title, report_df)
        
        return title, report_df

# --- Programı Çalıştırma Örneği ---
if __name__ == '__main__':
    # Örnek ABD Hisse Senetleri Listesi
    SAMPLE_TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'LUMN', 'PLTR', 'GME'] 

    # UYARI: Botunuzun token'ını ve chat ID'nizi buraya girmeyi unutmayın!
    # Aksi takdirde, Telegram gönderme kısmı hata verecektir.
    
    # --- AGRESİF STRATEJİ Testi ---
    print("\n" + "="*50)
    print(">>> AGRESİF STRATEJİ TARAMASI BAŞLATILIYOR <<<")
    print("="*50)
    
    screener_aggressive = DualStrategyScreener(
        tickers=SAMPLE_TICKERS, 
        strategy='AGRESİF',
        telegram_token=TELEGRAM_TOKEN,
        chat_id=CHAT_ID
    )
    title_agressive, report_agressive = screener_aggressive.run_screener()
    
    if report_agressive is not None:
        print("\n" + title_agressive)
        print("-" * len(title_agressive))
        print(report_agressive.to_markdown(index=False))

    # --- DENGELİ STRATEJİ Testi ---
    print("\n" + "="*50)
    print(">>> DENGELİ STRATEJİ TARAMASI BAŞLATILIYOR <<<")
    print("="*50)

    screener_balanced = DualStrategyScreener(
        tickers=SAMPLE_TICKERS, 
        strategy='DENGELİ',
        telegram_token=TELEGRAM_TOKEN,
        chat_id=CHAT_ID
    )
    title_balanced, report_balanced = screener_balanced.run_screener()
    
    if report_balanced is not None:
        print("\n" + title_balanced)
        print("-" * len(title_balanced))
        print(report_balanced.to_markdown(index=False)).futures import ThreadPoolExecutor, as_completed
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
