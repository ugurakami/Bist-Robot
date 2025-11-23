import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import ta 
from datetime import datetime, date

# --- AYARLAR ---
# GitHub Secrets'tan çekilir
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
HESAPLAMALAR_DOSYASI = "haftalik_pozisyonlar.json"

# RİSK VE PORTFÖY AYARLARI (USD cinsinden)
PORTFOY_BUYUKLUGU = 100_000   # Toplam portföy büyüklüğünüz (Örn: $100.000)
RISK_PER_TRADE = 0.01         # Her işlemde portföyün %1'ini riske et
CHECK_INDEX = False           # S&P 500 Endeks Kontrol Bayrağı (Dinamik tarama için False önerilir)


# --- YARDIMCI FONKSİYONLAR ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def save_positions(positions):
    with open(HESAPLAMALAR_DOSYASI, 'w') as f:
        json.dump(positions, f)

def load_positions():
    if os.path.exists(HESAPLAMALAR_DOSYASI):
        with open(HESAPLAMALAR_DOSYASI, 'r') as f:
            return json.load(f)
    return []

# --- DINAMIK LISTE ÇEKME (S&P 500) ---
def get_sp500_tickers():
    """Wikipedia'dan S&P 500 bileşenlerini çeker."""
    try:
        # Pandas'ın lxml ile web'den tablo okuma özelliği kullanılır
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        sp500_df = tables[0]
        tickers = sp500_df['Symbol'].tolist() 
        # Bazı tikler yfinance'da sorun çıkarabilir (. vs -), temizlenir
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        send_telegram(f"❌ HATA: S&P 500 listesi çekilemedi: {e}")
        return []

# --- SUPER TREND HESAPLAMA ---
def get_weekly_supertrend(symbol):
    try:
        # ABD piyasası için sonek YOK
        df = yf.download(symbol, period="2y", interval="1wk", progress=False) 
        if len(df) < 50: return None
        
        # SuperTrend Hesaplama (10, 3.0)
        st_data = ta.trend.supertrend(
            close=df['Close'], high=df['High'], low=df['Low'], window=10, coefficient=3.0
        )
        
        df = df.join(st_data)
        # ta kütüphanesi sütun adları kullanılır
        df['ST_Value'] = df['SUPERT_D_10_3.0'] 
        df['Trend'] = np.where(df['SUPERT_10_3.0'] > 0, 1, -1) 
        
        return df.dropna()

    except Exception as e:
        print(f"Veri çekme veya SuperTrend hesaplamasında hata oluştu ({symbol}): {e}")
        return None

# --- PAZAR TARAMASI (AL SİNYALİ) ---
def pazar_taramasi():
    report = f"📢 *PAZAR HAFTALIK ABD S&P 500 RAPORU* ({date.today().strftime('%d.%m.%Y')})\n\n"
    secilenler = []
    positions_to_save = []
    
    # *** DINAMIK LISTE ÇEKİLİYOR ***
    hisse_listesi = get_sp500_tickers()
    if not hisse_listesi:
        return

    # ENDEKS KONTROLÜ (Opsiyonel)
    if CHECK_INDEX:
        spy_df = get_weekly_supertrend("^GSPC") # S&P 500 endeksi
        if spy_df is None or spy_df['Trend'].iloc[-1] != 1:
            send_telegram("⚠️ *S&P 500 HAFTALIK TREN DÜŞÜŞTE* → Bu hafta ALIM YOK.")
            save_positions([])
            return

    for hisse in hisse_listesi:
        
        df = get_weekly_supertrend(hisse)
        if df is None: continue
        
        last = df.iloc[-1]
        st_val = last['ST_Value']
        
        # DÜŞÜK RİSKLİ GİRİŞ KOŞULU (Pullback: Trendde ve desteğe yakın)
        if last['Trend'] == 1 and last['Close'] < st_val * 1.15: 
            
            # --- POZİSYON BÜYÜKLÜĞÜ HESAPLAMA ---
            risk_per_share = last['Close'] - st_val 
            if risk_per_share <= 0: continue # Negatif risk olamaz
                
            max_risk_capital = PORTFOY_BUYUKLUGU * RISK_PER_TRADE
            
            # Alınacak adet (Quantity)
            adet = int(max_risk_capital // risk_per_share)
            
            if adet < 1: continue 
                
            pozisyon_degeri = adet * last['Close']
            
            # --- RAPOR VERİLERİ ---
            signal_text = (
                f"✅ *{hisse}*\n"
                f"Fiyat: ${last['Close']:.2f} | Stop: ${st_val:.2f}\n"
                f"**Alım Adeti:** {adet} adet\n"
                f"**Poz. Değeri:** ${pozisyon_degeri:,.0f} ({pozisyon_degeri/PORTFOY_BUYUKLUGU:.1%})\n"
            )
            
            secilenler.append(signal_text)
            
            positions_to_save.append({
                'hisse': hisse,
                'stop_fiyat': st_val
            })
            
            # En fazla 5 sinyal yeterli (performans için sınırlarız)
            if len(secilenler) >= 5: break 

    if secilenler:
        report += f"⭐ *YENİ HAFTALIK AL SİNYALLERİ* (Risk %{RISK_PER_TRADE*100:.0f}) ⭐\n"
        report += "".join(secilenler)
        report += "\n\n⚠️ _Yatırım tavsiyesi değildir. Robotik analiz sonucudur._"
    else:
        report += "Bu hafta uygun kriterde hisse bulunamadı. Nakitte kalmak mantıklı olabilir."

    send_telegram(report)
    save_positions(positions_to_save)


# --- PERŞEMBE KONTROLÜ (SAT SİNYALİ) ---
def persembe_kontrolu():
    positions = load_positions()
    
    if not positions:
        send_telegram("🗓️ *PERŞEMBE KONTROL:* Geçen haftadan takip edilecek pozisyon bulunamadı.")
        return

    rapor = f"🗓️ *PERŞEMBE KAPANIŞ KONTROLÜ (ABD)* ({date.today().strftime('%d.%m.%Y')})\n\n"
    kapananlar = []
    devam_edenler = []
    new_positions = []

    for pos in positions:
        hisse = pos['hisse']
        stop_fiyat = pos['stop_fiyat']
        
        df = get_weekly_supertrend(hisse)
        if df is None: continue
        
        last_close = df.iloc[-1]['Close']
        last_trend = df.iloc[-1]['Trend']
        
        # SAT SİNYALİ
        if last_trend == -1 or last_close < stop_fiyat:
            kapananlar.append(f"🔴 *{hisse}* → **KAPAT** (Fiyat: ${last_close:.2f}). Trend bozuldu / Stop-Loss'a değdi.")
        else:
            devam_edenler.append(f"🟢 *{hisse}* → **DEVAM** (Fiyat: ${last_close:.2f}). Trend sağlam.")
            new_positions.append(pos)

    if kapananlar:
        rapor += "*POZİSYON KAPATMA SİNYALLERİ*\n"
        rapor += "\n".join(kapananlar)
        rapor += "\n"
        
    if devam_edenler:
        rapor += "*DEVAM EDEN POZİSYONLAR*\n"
        rapor += "\n".join(devam_edenler)

    send_telegram(rapor)
    save_positions(new_positions)

# --- ANA KONTROL ---
if __name__ == "__main__":
    gun = datetime.now().weekday()
    
    if gun == 6: # Pazar
        print("Pazar Taraması Başlatılıyor...")
        pazar_taramasi()
    
    elif gun == 3: # Perşembe
        print("Perşembe Kontrolü Başlatılıyor...")
        persembe_kontrolu()
    
    else:
        print(f"Beklemede... Bugün işlem günü değil. (Pazar veya Perşembe bekleniyor)")
