import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import ta 
from datetime import datetime, date

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
HESAPLAMALAR_DOSYASI = "haftalik_pozisyonlar.json"

# RİSK VE PORTFÖY AYARLARI (USD cinsinden)
PORTFOY_BUYUKLUGU = 100_000   # Toplam portföy büyüklüğünüz (Örnek: $100.000)
RISK_PER_TRADE = 0.01         # Her işlemde portföyün %1'ini riske et (0.01)
ATR_STOP_CARPANI = 3.0        # Stop-Loss mesafesi (SuperTrend 3xATR kullanır)
CHECK_INDEX = False           # S&P 500 Endeks Kontrol Bayrağı

# ====================== ABD PİYASASI SEKTÖR LİSTESİ (Büyüme + Mega-Cap) ======================
SEKTORLER = {
    "YUKSEK_BUYUME": ["AMD", "COST", "NET", "SNOW", "MRNA", "SHOP", "SQ", "ROKU", "SPOT"],
    "TEKNOLOJI": ["MSFT", "AAPL", "GOOGL", "AMZN", "NVDA", "META", "ADBE", "TSM"],
    "ETFS": ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLP"], 
    "FINANS": ["JPM", "V", "MA", "BAC", "WFC", "GS", "MS"],
    "SAGLIK": ["JNJ", "PFE", "LLY", "MRK", "UNH", "ABBV"],
    "TUKETIM": ["WMT", "KO", "PEP", "COST", "PG", "MCD", "HD"],
    "ENERJI": ["XOM", "CVX", "SLB", "CAT", "BA", "HON"],
}
# ==================================================================================================

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

# --- SUPER TREND HESAPLAMA ---
def get_weekly_supertrend(symbol):
    try:
        # ABD piyasası için sonek YOK
        df = yf.download(symbol, period="2y", interval="1wk", progress=False) 
        if len(df) < 50: return None
        
        # ATR ve SuperTrend Hesaplama (ATR'yi pozisyon büyüklüğü için kullanıyoruz)
        df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=10)
        
        st_data = ta.trend.supertrend(
            close=df['Close'], high=df['High'], low=df['Low'], window=10, coefficient=3.0
        )
        
        df = df.join(st_data)
        df['ST_Value'] = df['SUPERT_D_10_3.0'] 
        df['Trend'] = np.where(df['SUPERT_10_3.0'] > 0, 1, -1) 
        
        return df.dropna()

    except Exception as e:
        print(f"Veri çekme veya SuperTrend hesaplamasında hata oluştu ({symbol}): {e}")
        return None

# --- PAZAR TARAMASI (AL SİNYALİ) ---
def pazar_taramasi():
    report = f"📢 *PAZAR HAFTALIK ABD RAPORU* ({date.today().strftime('%d.%m.%Y')})\n\n"
    secilenler = []
    used_sectors = set()
    positions_to_save = []

    # ENDEKS KONTROLÜ
    if CHECK_INDEX:
        spy_df = get_weekly_supertrend("SPY") # S&P 500 ETF kontrolü
        if spy_df is None or spy_df['Trend'].iloc[-1] != 1:
            send_telegram("⚠️ *S&P 500 HAFTALIK TREN DÜŞÜŞTE* → Bu hafta ALIM YOK.")
            save_positions([])
            return

    for sektor, hisseler in SEKTORLER.items():
        if len(used_sectors) >= 3: break
        
        for hisse in hisseler:
            if sektor in used_sectors: continue
            
            df = get_weekly_supertrend(hisse)
            if df is None: continue
            
            last = df.iloc[-1]
            st_val = last['ST_Value']
            
            # DÜŞÜK RİSKLİ GİRİŞ KOŞULU (Pullback)
            if last['Trend'] == 1 and last['Close'] < st_val * 1.15: 
                
                # --- POZİSYON BÜYÜKLÜĞÜ HESAPLAMA ---
                # 1. Hisse başına maksimum risk (stop mesafesi)
                risk_per_share = last['Close'] - st_val # Giriş fiyatı - Stop (ST değeri)
                if risk_per_share <= 0: continue # Negatif risk olamaz
                    
                # 2. Portföyden riske edilecek toplam miktar
                max_risk_capital = PORTFOY_BUYUKLUGU * RISK_PER_TRADE
                
                # 3. Alınacak adet (Quantity)
                adet = int(max_risk_capital // risk_per_share)
                
                if adet < 1: continue # 1 adetten az alım yapma
                    
                pozisyon_degeri = adet * last['Close']
                
                # --- RAPOR VERİLERİ ---
                hedef = last['Close'] * 1.15 
                stop = st_val 
                
                signal_text = (
                    f"✅ *{hisse}* ({sektor})\n"
                    f"Fiyat: ${last['Close']:.2f} | Stop: ${stop:.2f}\n"
                    f"**Alım Adeti:** {adet} adet\n"
                    f"**Poz. Değeri:** ${pozisyon_degeri:,.0f} ({pozisyon_degeri/PORTFOY_BUYUKLUGU:.1%})\n"
                )
                
                secilenler.append(signal_text)
                used_sectors.add(sektor)
                
                positions_to_save.append({
                    'hisse': hisse,
                    'stop_fiyat': stop
                })
                break

    if secilenler:
        report += f"⭐ *YENİ HAFTALIK AL SİNYALLERİ* (Risk %{RISK_PER_TRADE*100:.0f}) ⭐\n"
        report += "".join(secilenler)
        report += "\n\n⚠️ _Yatırım tavsiyesi değildir. Robotik analiz sonucudur._"
    else:
        report += "Bu hafta uygun kriterde hisse bulunamadı. Nakitte kalmak mantıklı olabilir."

    send_telegram(report)
    save_positions(positions_to_save)


# --- PERŞEMBE KONTROLÜ ve ANA KONTROL FONKSİYONLARI (Aynı Kalıyor) ---
def persembe_kontrolu():
    # ... (Bu kısım aynı kalır, sadece rapor başlığı ABD'ye uygun olmalıdır)
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
    
    if gun == 6:
        print("Pazar Taraması Başlatılıyor...")
        pazar_taramasi()
    
    elif gun == 3:
        print("Perşembe Kontrolü Başlatılıyor...")
        persembe_kontrolu()
    
    else:
        print(f"Beklemede... Bugün işlem günü değil. (Pazar veya Perşembe bekleniyor)")
