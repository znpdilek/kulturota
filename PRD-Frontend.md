# KültürRota — Frontend PRD v1.0
### Türkiye Kültürel Miras Keşif ve Sosyal Gezi Platformu

**Hazırlayan:** Senior Frontend Architect  
**Tarih:** Mayıs 2026  
**Backend API:** `http://localhost:8000/api/v1`  
**Teknoloji Yığını:** React 18 · Vite · Tailwind CSS · Axios · React Router DOM v6 · React-Leaflet · Framer Motion

---

## İçindekiler

1. [Proje Vizyonu & Tasarım Felsefesi](#1-proje-vizyonu--tasarım-felsefesi)
2. [Teknoloji Yığını & Araçlar](#2-teknoloji-yığını--araçlar)
3. [Proje Dizin Yapısı](#3-proje-dizin-yapısı)
4. [Tasarım Sistemi (Design System)](#4-tasarım-sistemi-design-system)
5. [Sayfa Yapısı & Ekranlar](#5-sayfa-yapısı--ekranlar)
6. [Component Hiyerarşisi](#6-component-hiyerarşisi)
7. [State Yönetimi & Servis Katmanı](#7-state-yönetimi--servis-katmanı)
8. [Routing Mimarisi](#8-routing-mimarisi)
9. [API Entegrasyon Rehberi](#9-api-entegrasyon-rehberi)
10. [Geliştirme Yol Haritası (Fazlandırma)](#10-geliştirme-yol-haritası-fazlandırma)
11. [Performans & Erişilebilirlik Standartları](#11-performans--erişilebilirlik-standartları)
12. [Test Stratejisi](#12-test-stratejisi)

---

## 1. Proje Vizyonu & Tasarım Felsefesi

### 1.1 Ürün Tanımı
KültürRota, kullanıcıların Türkiye'nin zengin kültürel mirasını harita üzerinde keşfetmesini, kendi gezi rotalarını oluşturmasını ve bu rotaları toplulukla paylaşmasını sağlayan sosyal bir platformdur. Temel değer önerisi: **"Haritanı çiz, mirasını keşfet, deneyimini paylaş."**

### 1.2 Hedef Kullanıcı Segmentleri
| Segment | Profil | Birincil İhtiyaç |
|---|---|---|
| **Kültür Gezgini** | 25-45 yaş, tarihe meraklı | Mekan keşfi ve rota takibi |
| **Turist** | Yabancı / şehir dışı ziyaretçi | Hızlı rota önerisi, harita navigasyonu |
| **İçerik Üreticisi** | Blog / sosyal medya aktif | Rota oluşturma, beğeni ve yorum |
| **Akademisyen** | Araştırmacı / öğrenci | Detaylı mekan bilgisi, UNESCO filtreleme |

### 1.3 Tasarım Felsefesi: "Taş Dokulu Dijital Atlas"
Tasarım dili, Anadolu'nun mimari ve el sanatı mirasından ilham alır. Hamleli çizgiler, toprak renk skalası ve organik dokular modern bir yalınlıkla buluşur. Jenerik "SaaS mavi" estetikten kesinlikle kaçınılır.

**Anahtar Prensipler:**
- **Yüzey ve Derinlik:** Harita her zaman birincil anlatı aracıdır; UI elementleri haritanın üzerine ince bir katman olarak oturur
- **Organik Asimetri:** Grid-kıran, kitap sayfası gibi yatay akışlar
- **Bilgi Yoğunluğu ile Nefes Dengesi:** Kart odaklı, geniş beyaz alanlı yerleşim
- **Coğrafi Kimlik:** Renk skalası Anadolu topraklarından, Osmanlı çinisinden ve Ege mavilerinden türetilmiştir

---

## 2. Teknoloji Yığını & Araçlar

### 2.1 Çekirdek Kütüphaneler

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.0",
    "react-leaflet": "^4.2.1",
    "leaflet": "^1.9.4",
    "framer-motion": "^11.0.0",
    "@tanstack/react-query": "^5.17.0",
    "zustand": "^4.5.0",
    "react-hook-form": "^7.49.0",
    "zod": "^3.22.0",
    "@hookform/resolvers": "^3.3.0",
    "react-hot-toast": "^2.4.1",
    "date-fns": "^3.3.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "vitest": "^1.2.0",
    "@testing-library/react": "^14.2.0"
  }
}
```

### 2.2 Harita Kütüphanesi Kararı

**Seçim: React-Leaflet (OSM tabanlı)**

| Kriter | React-Leaflet | Mapbox GL |
|---|---|---|
| Maliyet | Ücretsiz | Token limiti var |
| OSM uyumu | Doğal (PRD §20 ODbL) | Mümkün ama ek çaba |
| Bundle boyutu | ~140KB | ~250KB |
| Custom tile | Evet (Stamen/Carto) | Evet (Mapbox Studio) |
| **Karar** | ✅ **Seçildi** | — |

**Önerilen tile provider:** `CartoDB.Voyager` — açık renk, detaylı Türkiye verisi, hafif görünüm.

---

## 3. Proje Dizin Yapısı

```
kulturota-frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── assets/               # SVG ikonlar, illüstrasyonlar, maskot
│   ├── components/
│   │   ├── ui/               # Atomik bileşenler (Button, Input, Badge, Modal…)
│   │   ├── map/              # Harita bileşenleri (MapContainer, MarkerCluster…)
│   │   ├── place/            # Mekan kartları, detay panelleri
│   │   ├── route/            # Rota kartları, stop listesi, rota çizgisi
│   │   ├── review/           # Yorum formu, yorum listesi, yıldız rating
│   │   └── layout/           # Navbar, Footer, Sidebar, PageWrapper
│   ├── pages/
│   │   ├── HomePage.jsx
│   │   ├── auth/
│   │   │   ├── LoginPage.jsx
│   │   │   └── RegisterPage.jsx
│   │   ├── explore/
│   │   │   └── ExplorePage.jsx
│   │   ├── routes/
│   │   │   ├── RouteBuilderPage.jsx
│   │   │   ├── RouteDetailPage.jsx
│   │   │   └── MyRoutesPage.jsx
│   │   ├── profile/
│   │   │   └── ProfilePage.jsx
│   │   └── NotFoundPage.jsx
│   ├── hooks/                # Custom hooks (useAuth, useMap, usePlaces…)
│   ├── services/             # Axios servis fonksiyonları (api katmanı)
│   │   ├── api.js            # Axios instance, interceptors
│   │   ├── authService.js
│   │   ├── placeService.js
│   │   ├── routeService.js
│   │   ├── reviewService.js
│   │   └── photoService.js
│   ├── store/                # Zustand store'ları
│   │   ├── authStore.js
│   │   ├── mapStore.js
│   │   └── routeBuilderStore.js
│   ├── utils/                # Yardımcı fonksiyonlar
│   ├── constants/            # Kategori renkleri, sabit değerler
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── tailwind.config.js
├── vite.config.js
└── .env.example
```

---

## 4. Tasarım Sistemi (Design System)

### 4.1 Renk Paleti

```css
/* tailwind.config.js → extend.colors */

:root {
  /* Ana Renkler — Anadolu Toprak Skalası */
  --color-obsidian:    #1A1614;   /* Metin, başlık */
  --color-sienna:      #A0522D;   /* Birincil CTA (Toprak kırmızı) */
  --color-amber:       #D4883A;   /* Hover, vurgu */
  --color-sand:        #F2E8D9;   /* Arka plan, kart zemini */
  --color-cream:       #FAF7F2;   /* Sayfa arka planı */

  /* Aksanlar — Çini & Ege */
  --color-turquoise:   #2A9D8F;   /* UNESCO rozeti, onay */
  --color-indigo-tile: #264653;   /* Harita overlay, koyu vurgu */
  --color-rose-rug:    #E76F51;   /* Hata, uyarı, beğeni ikonu */

  /* Nötraller */
  --color-stone-100:   #F5F0EA;
  --color-stone-200:   #E8DDD0;
  --color-stone-400:   #9E8E7E;
  --color-stone-600:   #6B5B4E;
  --color-stone-800:   #3D2E26;
}
```

**Renk Kullanım Kuralları:**
- `sienna` → birincil butonlar, aktif sekmeler, link rengi
- `turquoise` → UNESCO rozeti, başarı durumu, harita polilini
- `rose-rug` → beğeni (like) ikonu, silme onayı, kritik uyarı
- `indigo-tile` → harita kontrol paneli, koyu sidebar
- `sand / cream` → kart arka planları, form alanları

### 4.2 Tipografi

```js
// tailwind.config.js
fontFamily: {
  display: ['"Playfair Display"', 'Georgia', 'serif'],  // Başlıklar (H1-H3)
  body:    ['"Lora"', 'Georgia', 'serif'],               // Paragraf metni
  ui:      ['"DM Sans"', 'sans-serif'],                  // Buton, etiket, navigasyon
  mono:    ['"JetBrains Mono"', 'monospace'],            // Koordinat, UUID
}
```

**Google Fonts import:**
```html
<link href="https://fonts.googleapis.com/css2?
  family=Playfair+Display:wght@700;900&
  family=Lora:wght@400;500&
  family=DM+Sans:wght@400;500;600&
  display=swap" rel="stylesheet">
```

**Tipografi Ölçeği:**

| Token | Font | Boyut | Kullanım |
|---|---|---|---|
| `display-2xl` | Playfair Display 900 | 4.5rem | Hero başlık |
| `display-xl` | Playfair Display 700 | 3rem | Sayfa başlığı |
| `display-lg` | Playfair Display 700 | 2rem | Bölüm başlığı |
| `body-lg` | Lora 400 | 1.125rem | Mekan açıklaması |
| `body-md` | Lora 400 | 1rem | Genel içerik |
| `ui-sm` | DM Sans 500 | 0.875rem | Etiket, meta |
| `ui-xs` | DM Sans 400 | 0.75rem | Yardımcı metin |

### 4.3 Spacing & Border Radius

```js
// Tailwind extend
spacing: {
  '18': '4.5rem',
  '22': '5.5rem',
  '72': '18rem',
  '84': '21rem',
  '96': '24rem',
},
borderRadius: {
  'organic': '2rem 0.5rem 2rem 0.5rem',  // Asimetrik köşe — imza element
  'card': '0.75rem',
  'badge': '9999px',
}
```

### 4.4 Gölge & Yüzey Sistemi

```css
/* Kart gölgeleri — toprak tonlu */
.shadow-card    { box-shadow: 0 2px 8px rgba(160,82,45,0.08), 0 1px 2px rgba(0,0,0,0.06); }
.shadow-card-hover { box-shadow: 0 8px 24px rgba(160,82,45,0.15), 0 2px 6px rgba(0,0,0,0.08); }
.shadow-map-control { box-shadow: 0 4px 16px rgba(38,70,83,0.2); }
```

### 4.5 Animasyon Rehberi (Framer Motion)

```js
// src/utils/animations.js — paylaşılan animasyon varyantları

export const fadeUp = {
  hidden:  { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } }
};

export const staggerContainer = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.08 } }
};

export const slideInFromLeft = {
  hidden:  { opacity: 0, x: -32 },
  visible: { opacity: 1, x: 0,  transition: { duration: 0.4, ease: 'easeOut' } }
};

export const scaleOnHover = {
  rest:  { scale: 1 },
  hover: { scale: 1.03, transition: { duration: 0.2 } }
};

export const mapPanelSlide = {
  hidden:  { opacity: 0, x: '100%' },
  visible: { opacity: 1, x: '0%',    transition: { type: 'spring', damping: 28, stiffness: 300 } },
  exit:    { opacity: 0, x: '100%',  transition: { duration: 0.25 } }
};
```

**Animasyon Kuralları:**
- Sayfa geçişleri: `fadeUp` varyantı, 350ms
- Kart listeleri: `staggerContainer + fadeUp`, 80ms gecikme
- Harita yan paneli: `mapPanelSlide` (spring fizik)
- Buton hover: CSS `transition-all duration-200` (Framer gerekmez)
- Rota çizgisi: Leaflet polyline + CSS stroke-dasharray animasyonu

### 4.6 İkon Kütüphanesi
**Seçim: Lucide React** — minimal, tutarlı, tree-shakable

```bash
npm install lucide-react
```

**Özel harita ikonları:** SVG tabanlı Leaflet `DivIcon` — Tailwind ile stillendirilmiş özel pin şekilleri (kategori bazlı renk).

---

## 5. Sayfa Yapısı & Ekranlar

---

### 5.1 Ana Sayfa — `HomePage.jsx`

**URL:** `/`  
**Erişim:** Herkese açık

**Bölümler:**

#### Hero Section
- **Başlık:** "Anadolu'nun Hafızasını Keşfet" (Playfair Display, büyük punto)
- **Alt Başlık:** "Kültürel miras mekanlarını keşfet, kendi rotanı çiz, deneyimini paylaş."
- **CTA Butonlar:** `[Rotaları Keşfet]` (sienna, filled) · `[Rota Oluştur]` (outlined)
- **Arka Plan:** Subtle Türkiye haritası SVG kontur + toprak renkli gradient overlay
- **Animasyon:** Başlık ve butonlar `fadeUp` ile sıralı giriş (stagger 150ms)

#### Arama & Filtreleme Çubuğu
```
[ 🔍 Mekan veya rota ara... ] [Kategori ▼] [UNESCO ☐] [Ara]
```
- Kategori filtresi: `museum`, `archaeological_site`, `mosque`, `palace`, `historic`, `church`
- Arama debounce: 400ms
- API: `GET /api/v1/places?q={query}&category={cat}&unesco={bool}`

#### Öne Çıkan Rotalar Bölümü
- Başlık: "Topluluktan Rotalar"
- 3'lü kart grid (responsive: 1→2→3 kolon)
- Her **RouteCard** içeriği:
  - Kapak fotoğrafı (aspect-ratio 16:9)
  - Rota adı (Playfair Display Medium)
  - Yazar avatar + username
  - Stop sayısı · Tahmini süre · Beğeni sayısı
  - Zorluk badge (easy/moderate/hard → renk kodlu)
- Animasyon: Scroll-triggered `staggerContainer`

#### Kategori Vitrin Bölümü
- Yatay scroll (overflow-x: auto, snap-x) üzerinde 6 kategori kartı
- Her kart: SVG ikon + isim + mekan sayısı
- Tıklanınca `/explore?category={cat}` sayfasına yönlendirme

#### İstatistik Bantı
```
[1.200+ Mekan]   [450+ Rota]   [32+ Şehir]   [UNESCO Mirası: 21]
```
- Sayı sayacı animasyonu (Intersection Observer + `requestAnimationFrame`)

---

### 5.2 Auth Sayfaları

#### 5.2.1 Giriş Sayfası — `auth/LoginPage.jsx`
**URL:** `/giris`

**Layout:** İki sütun — sol: görsel (harita detayı / antik fresk fotoğrafı), sağ: form

**Form Alanları:**
```
E-posta veya kullanıcı adı *
Şifre *
[Beni hatırla]                    [Şifremi unuttum]
[Giriş Yap]                       — CTA primary button
```

**API:** `POST /api/v1/auth/login`  
**Validasyon:** Zod schema → `identifier` min 3, `password` min 1  
**Başarı:** Token'ları localStorage'a kaydet → `/` yönlendir  
**Hata:** Toast notification + form error state

#### 5.2.2 Kayıt Sayfası — `auth/RegisterPage.jsx`
**URL:** `/kayit`

**Form Alanları:**
```
E-posta *
Kullanıcı Adı * (3-30 karakter, sadece harf/rakam/alt çizgi)
Şifre * (min 10 karakter)
Doğum Tarihi * (18+ zorunlu — PRD D3)
[✓] KVKK Aydınlatma Metnini okudum ve onaylıyorum *
[Hesap Oluştur]
```

**API:** `POST /api/v1/auth/register`  
**18+ Uyarısı:** Doğum tarihi < 18 yıl ise form submit engellenir, inline hata gösterilir  
**KVKK:** Checkbox işaretlenmeden submit engellenir, zorunlu alan hatası  
**Başarı:** Otomatik login → `/` yönlendir

---

### 5.3 Keşfet & Harita Sayfası — `explore/ExplorePage.jsx`

**URL:** `/kesfet`  
**Erişim:** Herkese açık

**Layout:** Full-screen split — Sol: Filtre paneli + Liste (1/3), Sağ: Harita (2/3)

```
┌─────────────────┬────────────────────────────────────┐
│  FİLTRE PANELİ  │                                    │
│  ─────────────  │          🗺️  LEAFlET HARİTA         │
│  Arama kutusu   │                                    │
│  Kategori chips │    [📍 pin] [📍 pin] [📍 pin]      │
│  UNESCO toggle  │                                    │
│  Mesafe slider  │                                    │
│  ─────────────  │                                    │
│  MEKAN LİSTESİ  │                                    │
│  (scroll)       │                                    │
│  PlaceCard x N  │                                    │
└─────────────────┴────────────────────────────────────┘
```

**Harita Özellikleri:**
- Tile: CartoDB Voyager
- Başlangıç merkezi: Türkiye merkezi (`[39.0, 35.0]`), zoom 6
- **Marker clustering:** Leaflet.markercluster eklentisi
- **Kategori bazlı pin rengi:**
  - `museum` → turquoise
  - `archaeological_site` → amber  
  - `mosque` → indigo-tile
  - `palace` → sienna
  - `historic` → stone-600
  - Diğer → stone-400
- **UNESCO rozeti:** Altın yıldız overlay pin üzerinde
- Pin tıklama → Sağda **PlaceDetailPanel** kayar (Framer Motion `mapPanelSlide`)

**Filtre Davranışı:**
- Filtre değişiminde `GET /api/v1/places?{params}` çağrısı (debounce 300ms)
- bbox filtresi: haritanın görünür alanı (map bounds) otomatik gönderilir
- "Benim Konumum" butonu: `navigator.geolocation` → `GET /api/v1/places/nearby?lat=&lng=&radius=`

**PlaceDetailPanel (harita üzerinde yan panel):**
- Animasyonlu giriş (sağdan kayar)
- Mekan adı · Kategori badge · UNESCO işareti
- Kapak fotoğrafı
- Kısa açıklama (max 3 satır)
- "Rotaya Ekle" butonu (auth zorunlu → modal)
- "Detayı Gör" linki → `/mekanlar/{slug}`
- API: `GET /api/v1/places/{place_id}`

---

### 5.4 Rota Oluşturucu — `routes/RouteBuilderPage.jsx`

**URL:** `/rota-olustur`  
**Erişim:** Giriş zorunlu (Auth Guard)

Bu sayfanın aynı `/rota/:id/duzenle` URL'i üzerinden düzenleme modu da desteklemesi gerekir.

**Layout (3 Bölge):**

```
┌──────────────┬────────────────────────────────┬───────────────────┐
│ ROTA BİLGİSİ │                                │  STOP LİSTESİ     │
│ ──────────── │     🗺️  ETKİLEŞİMLİ HARİTA     │  ────────────────  │
│ Başlık       │                                │  [Sürükle & sırala]│
│ Açıklama     │   [📍seçili] [📍seçili]        │                    │
│ Tema         │    ────polyline────            │  1. Ayasofya       │
│ Zorluk       │                                │  2. Topkapı        │
│ Gizlilik     │                                │  3. Kapalıçarşı    │
│ ──────────── │                                │  ────────────────  │
│ Mekan Arama  │                                │  [Rota Oluştur]    │
│ [ Ara... ]   │                                │  [Taslak Kaydet]   │
│ Sonuç listesi│                                │                    │
└──────────────┴────────────────────────────────┴───────────────────┘
```

**Sol Panel — Rota Bilgisi Formu:**
```
Rota Başlığı *              (min 3, max 200 karakter)
Açıklama                    (opsiyonel, textarea, çok dilli)
Tema                        (serbest metin, max 80 karakter)
Zorluk          [Kolay] [Orta] [Zor]   (segmented control)
Kapak Görseli   [URL gir veya fotoğraf yükle]
Herkese Açık    [toggle switch]
```

**Sol Panel — Mekan Arama:**
```
[ 🔍 Rotaya mekan ekle... ]    (debounce 300ms)
↓  Arama sonuçları (PlaceRow):
   📍 Ayasofya · Cami · İstanbul    [+Ekle]
   📍 Topkapı Sarayı · Saray · İst  [+Ekle]
```
API: `GET /api/v1/places?q={query}&limit=8`

**Orta Alan — Etkileşimli Harita:**
- Eklenen stop'lar numara etiketli özel pin ile gösterilir
- Stop'lar arası **polyline** çizilir (turquoise renk, animasyonlu stroke-dasharray)
- Haritaya tıklayarak `GET /api/v1/places/nearby?lat=&lng=&radius=500` ile yakın mekan arama
- Harita üzerinde mekan kartı mini popup: `[Rotaya Ekle]` butonu

**Sağ Panel — Stop Listesi (Sürükle & Bırak):**
- `@dnd-kit/sortable` ile sıralanable liste
- Her stop satırı:
  - Numaralı drag handle
  - Mekan adı + kategori ikonu
  - Tahmini konaklama süresi (opsiyonel, dakika input)
  - Not alanı (opsiyonel, collapse/expand)
  - Çıkar butonu (×)
- Sıra değişince `PATCH /api/v1/routes/{id}/stops` çağrısı (otomatik kayıt)

**Kaydetme Akışı:**
1. "Taslak Kaydet" → `POST /api/v1/routes` (`is_public: false`)
2. Stop ekleme → `POST /api/v1/routes/{id}/stops`
3. "Yayınla" → `PUT /api/v1/routes/{id}` (`is_public: true`)
4. Başarı → `/rota/{id}` sayfasına yönlendir + confetti animasyonu

**UX Özel Durumlar:**
- Minimum 2 stop uyarısı: 0-1 stop ile "Yayınla" engellenir
- Maksimum 250 stop: 250'ye ulaşınca "+ Ekle" butonu devre dışı
- Sayfa terk uyarısı: `window.beforeunload` event + modal

---

### 5.5 Rota Detay Sayfası — `routes/RouteDetailPage.jsx`

**URL:** `/rota/:route_id`  
**Erişim:** Herkese açık (public rotalar) | Sahip: özel rotalar da görünür

**Layout (İki Bölge + Alt Sekme):**

```
┌─────────────────────────────────────────────────────────────────┐
│  ROTA KAPAK BANNER (tam genişlik, 340px yükseklik)              │
│  [Kapak foto overlay] Rota adı  ♥ 248  ⭐ 4.2  🚶 Orta         │
│                                                                  │
│  [Profil] @yazar_adi  |  4 Durak  |  ~2.5 saat  |  Istanbul    │
└─────────────────────────────────────────────────────────────────┘
┌───────────────────────────────────┬─────────────────────────────┐
│  DURAK LİSTESİ (sıralı)          │  HARİTA (polyline + pinler)│
│  ─────────────────────────────── │                             │
│  1 → Ayasofya                    │   [📍1]──────[📍2]         │
│      30 dk · "Erken git!"        │         ↘                   │
│  2 → Topkapı Sarayı              │           [📍3]──[📍4]     │
│      90 dk · "Hazine bölümü..."  │                             │
│  3 → Kapalı Çarşı               │                             │
│      60 dk                       │                             │
│  ─────────────────────────────── │                             │
│  [♥ Beğen] [📋 Kopyala] [↗ Pay.] │                             │
└───────────────────────────────────┴─────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  [Yorumlar (12)] sekme                                           │
│  ─────────────────────────────────────────────────────────────  │
│  [Yorum Yaz formu — auth zorunlu]                               │
│  YorumKartı · YorumKartı · …                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Beğeni (Like) Bileşeni:**
- API: `GET /api/v1/routes/{id}/likes` (durum sorgulama)
- Beğen: `POST /api/v1/routes/{id}/likes` (idempotent)
- Geri çek: `DELETE /api/v1/routes/{id}/likes`
- Animasyon: kalp ikonu scale + fill animasyonu (Framer Motion spring)
- Auth yoksa: Modal ile "Giriş yapın" uyarısı

**Durak Haritası:**
- Her stop için numaralı pin (sienna rengi)
- Stop'lar arası polyline (turquoise, gestured opacity)
- Harita pin tıklama → inline popup ile mekan özet bilgisi
- "Tüm rotayı göster" (fitBounds) butonu

**Yorum Bölümü (Place Reviews — mekanlar üzerinden):**
- Not: Route review ayrı API endpoint'i yoktur; bu bölüm rotanın durak mekanlarının yorumlarını gösterir veya ileriki fazda `route_comments` eklenebilir.
- MVP'de: Kullanıcılar rotanın ilk durağının mekanına yorum yazabilir
- Yorum Formu:
  ```
  Puan: ⭐⭐⭐⭐⭐ (1-5, tıklanabilir)
  Yorum: [textarea, 5-2000 karakter]
  Ziyaret Tarihi: [date picker, opsiyonel]
  [Gönder]
  ```
  API: `POST /api/v1/places/{place_id}/reviews`
- Yorum Listesi: avatar + username + puan + tarih + metin, `GET /api/v1/places/{place_id}/reviews`

**Sahip Aksiyonları (route.owner_id === currentUser.id):**
- "Düzenle" butonu → `/rota/:id/duzenle`
- "Sil" butonu → onay modal → `DELETE /api/v1/routes/{id}`

---

### 5.6 Rotalarım Sayfası — `routes/MyRoutesPage.jsx`

**URL:** `/rotalarim`  
**Erişim:** Giriş zorunlu

- Kullanıcının rotaları iki sekme altında: **Yayında** · **Taslak**
- API: `GET /api/v1/routes`
- Kart başına: düzenle / sil / gizlilik toggle aksiyonları
- Boş durum: "Henüz rota oluşturmadınız" ilustrasyonu + CTA

---

### 5.7 Profil Sayfası — `profile/ProfilePage.jsx`

**URL:** `/profil`  
**Erişim:** Giriş zorunlu

**Sekmeler:**
1. **Profilim** — ad, kullanıcı adı, avatar güncelleme (`PUT /api/v1/users/me`)
2. **Gizlilik & KVKK** — veri dışa aktarma (`GET /api/v1/users/me/export-data`), hesap silme
3. **Oturum Güvenliği** — aktif oturumlar, şifre sıfırlama (ileriki faz)

**Hesap Silme Akışı:**
- Kırmızı tehlike bölgesi
- Onay metni input: `HESABIMI KALICI OLARAK SİL`
- API: `DELETE /api/v1/users/me`
- Başarı: Tüm store temizlenir, `/` yönlendirilir

---

## 6. Component Hiyerarşisi

### 6.1 Atomik UI Bileşenleri (`src/components/ui/`)

```
Button
├── variant: primary | secondary | ghost | danger
├── size: sm | md | lg
└── loading: boolean (spinner state)

Input
├── label, error, hint props
└── icon: leading/trailing

Badge
├── variant: category | unesco | difficulty | status
└── color: otomatik kategori rengi maplemesi

Avatar
├── src, alt, size props
└── fallback: baş harfi

Modal
├── isOpen, onClose, title
└── Framer Motion AnimatePresence ile animasyonlu

Toast (react-hot-toast wrapper)
├── success | error | warning | info
└── Özel stil: toprak rengi arka plan

StarRating
├── value (1-5), interactive: boolean
└── onChange callback

Spinner
└── size: sm | md | lg

EmptyState
├── illustration, title, description
└── action: CTA butonu

Pagination
└── offset/limit tabanlı
```

### 6.2 Mekan Bileşenleri (`src/components/place/`)

```
PlaceCard                    → Liste ve grid görünümü için
PlaceRow                     → Arama sonucu satırı (rota builder)
PlaceDetailPanel             → Harita yan paneli (kayar)
PlaceMiniPopup               → Harita marker popup
PlaceCategoryBadge           → Renk kodlu kategori etiketi
```

### 6.3 Rota Bileşenleri (`src/components/route/`)

```
RouteCard                    → Ana sayfa ve listeleme
RouteStopItem                → Sürükle-bırak stop satırı
RoutePolyline                → React-Leaflet polyline wrapper
RouteStopMarker              → Numaralı harita pini
RouteLikeButton              → Kalp ikonu + animasyon + sayaç
RouteDifficultyBadge         → easy/moderate/hard renk kodlu
```

### 6.4 Harita Bileşenleri (`src/components/map/`)

```
KulturoMap                   → Ana Leaflet konteyner wrapper
MapControls                  → Zoom, konum, katman seçimi
MarkerClusterGroup           → Mekan kümeleme
CategoryMarker               → Kategori bazlı özel pin
BoundsListener               → Harita alanı değişince filtre tetikler
```

### 6.5 Layout Bileşenleri (`src/components/layout/`)

```
Navbar
├── Logo (SVG)
├── Ana navigasyon linkleri
├── Auth durumuna göre: [Giriş/Kayıt] veya [Avatar + Dropdown]
└── Mobil: hamburger menü + slide drawer

Footer
├── Site linkleri, hakkında, KVKK
└── OSM/ODbL attribution (PRD §20 zorunluluğu)

AuthGuard
└── Giriş yoksa /giris?redirect= yönlendir

PageWrapper
├── Framer Motion pageTransition
└── Breadcrumb desteği
```

---

## 7. State Yönetimi & Servis Katmanı

### 7.1 Zustand Store'ları

#### `authStore.js`
```js
{
  user: null | UserMe,
  accessToken: null | string,
  refreshToken: null | string,
  isAuthenticated: boolean,

  // Actions
  login: (tokenPair, user) => void,
  logout: () => void,          // Token revoke + store temizle
  updateUser: (partial) => void,
  refreshAccessToken: () => Promise<void>,
}
```

#### `mapStore.js`
```js
{
  center: [39.0, 35.0],
  zoom: 6,
  bounds: null,
  selectedPlaceId: null,
  filters: { q, category, unesco, radius },

  // Actions
  setCenter, setZoom, setBounds,
  selectPlace, clearSelection,
  updateFilters,
}
```

#### `routeBuilderStore.js`
```js
{
  routeId: null,          // Kayıt sonrası UUID
  title: '',
  description: {},
  theme: '',
  isPublic: false,
  difficulty: null,
  stops: [],              // RouteStopWithPlace[]
  isDirty: boolean,       // Kaydedilmemiş değişiklik var mı

  // Actions
  setMeta, addStop, removeStop, reorderStops,
  loadExistingRoute,      // Düzenleme modu
  reset,
}
```

### 7.2 Axios Instance & Interceptors

```js
// src/services/api.js

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 10_000,
});

// Request: Access token ekle
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response: 401 → token yenile → retry
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true;
      await useAuthStore.getState().refreshAccessToken();
      return api(err.config);
    }
    return Promise.reject(err);
  }
);
```

### 7.3 React Query Yapılandırması

```js
// Query key factory
export const queryKeys = {
  places: {
    all:    () => ['places'],
    list:   (filters) => ['places', 'list', filters],
    detail: (id) => ['places', id],
    nearby: (params) => ['places', 'nearby', params],
  },
  routes: {
    all:    () => ['routes'],
    myList: () => ['routes', 'mine'],
    detail: (id) => ['routes', id],
    stops:  (id) => ['routes', id, 'stops'],
    likes:  (id) => ['routes', id, 'likes'],
  },
  reviews: {
    list: (placeId) => ['reviews', placeId],
  }
};

// Varsayılan ayarlar
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,   // 5 dakika
      gcTime:    10 * 60 * 1000,  // 10 dakika
      retry: 1,
    }
  }
});
```

---

## 8. Routing Mimarisi

```jsx
// src/App.jsx

<BrowserRouter>
  <Routes>
    {/* Public sayfalar */}
    <Route path="/"           element={<HomePage />} />
    <Route path="/kesfet"     element={<ExplorePage />} />
    <Route path="/giris"      element={<LoginPage />} />
    <Route path="/kayit"      element={<RegisterPage />} />

    {/* Auth zorunlu sayfalar */}
    <Route element={<AuthGuard />}>
      <Route path="/rota-olustur"       element={<RouteBuilderPage />} />
      <Route path="/rota/:id/duzenle"   element={<RouteBuilderPage editMode />} />
      <Route path="/rotalarim"          element={<MyRoutesPage />} />
      <Route path="/profil"             element={<ProfilePage />} />
    </Route>

    {/* Public rota/mekan detayları */}
    <Route path="/rota/:route_id"       element={<RouteDetailPage />} />

    {/* 404 */}
    <Route path="*" element={<NotFoundPage />} />
  </Routes>
</BrowserRouter>
```

**Sayfa Geçiş Animasyonu:**
```jsx
// PageWrapper.jsx
<AnimatePresence mode="wait">
  <motion.div
    key={location.pathname}
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{    opacity: 0, y: -8 }}
    transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
  >
    {children}
  </motion.div>
</AnimatePresence>
```

---

## 9. API Entegrasyon Rehberi

### 9.1 Auth Servisi

```js
// authService.js
export const authService = {
  register: (data) => api.post('/auth/register', data),
  login:    (data) => api.post('/auth/login', data),
  refresh:  (token) => api.post('/auth/refresh', { refresh_token: token }),
  logout:   (token) => api.post('/auth/logout', { refresh_token: token }),
  getMe:    () => api.get('/users/me'),
  updateMe: (data) => api.put('/users/me', data),
  deleteMe: (data) => api.delete('/users/me', { data }),
  exportData: () => api.get('/users/me/export-data'),
};
```

### 9.2 Mekan Servisi

```js
// placeService.js
export const placeService = {
  list:   (params) => api.get('/places', { params }),
  nearby: (params) => api.get('/places/nearby', { params }),
  detail: (id)     => api.get(`/places/${id}`),
};
```

### 9.3 Rota Servisi

```js
// routeService.js
export const routeService = {
  create:      (data)           => api.post('/routes', data),
  list:        (params)         => api.get('/routes', { params }),
  detail:      (id)             => api.get(`/routes/${id}`),
  update:      (id, data)       => api.put(`/routes/${id}`, data),
  delete:      (id)             => api.delete(`/routes/${id}`),
  // Stops
  listStops:   (id)             => api.get(`/routes/${id}/stops`),
  addStop:     (id, data)       => api.post(`/routes/${id}/stops`, data),
  updateStop:  (id, sid, data)  => api.patch(`/routes/${id}/stops/${sid}`, data),
  removeStop:  (id, sid)        => api.delete(`/routes/${id}/stops/${sid}`),
  // Likes
  getLikes:    (id)             => api.get(`/routes/${id}/likes`),
  like:        (id)             => api.post(`/routes/${id}/likes`),
  unlike:      (id)             => api.delete(`/routes/${id}/likes`),
};
```

### 9.4 Yorum Servisi

```js
// reviewService.js
export const reviewService = {
  list:   (placeId, params) => api.get(`/places/${placeId}/reviews`, { params }),
  create: (placeId, data)   => api.post(`/places/${placeId}/reviews`, data),
  delete: (placeId, id)     => api.delete(`/places/${placeId}/reviews/${id}`),
};
```

### 9.5 Hata Yönetimi Standartları

```js
// Merkezi hata handler
export function handleApiError(error) {
  const status  = error?.response?.status;
  const message = error?.response?.data?.detail || 'Bir hata oluştu.';

  const errorMap = {
    400: () => toast.error(message),
    401: () => toast.error('Oturum süresi doldu, lütfen tekrar giriş yapın.'),
    403: () => toast.error('Bu işlem için yetkiniz yok.'),
    404: () => toast.error('İstenen kaynak bulunamadı.'),
    409: () => toast.error(message), // Çakışma — yorum zaten var vb.
    413: () => toast.error('Dosya boyutu 5MB sınırını aşıyor.'),
    415: () => toast.error('Sadece JPG ve PNG dosyaları kabul edilir.'),
    422: () => toast.error('Lütfen form alanlarını kontrol edin.'),
    500: () => toast.error('Sunucu hatası, lütfen daha sonra tekrar deneyin.'),
  };

  (errorMap[status] || errorMap[500])();
}
```

---

## 10. Geliştirme Yol Haritası (Fazlandırma)

### Faz 1 — Temel Kurulum & Auth
**Tahmini Süre:** 3-4 gün

**Hedefler:**
- [ ] Vite + React + Tailwind + PostCSS kurulumu
- [ ] `tailwind.config.js` — renk paleti, font ailesi, extend değerleri
- [ ] `index.css` — CSS değişkenleri, temel reset, Google Fonts import
- [ ] Klasör yapısı oluşturma
- [ ] Axios instance + interceptorlar (`api.js`)
- [ ] Zustand `authStore` kurulumu
- [ ] React Query `QueryClient` konfigürasyonu
- [ ] **Navbar ve Footer** layout bileşenleri
- [ ] `AuthGuard` HOC
- [ ] **LoginPage** — form + API entegrasyonu + token saklama
- [ ] **RegisterPage** — form + 18+ validasyon + KVKK checkbox
- [ ] Token refresh akışı
- [ ] `react-hot-toast` kurulum ve global hata handler

**Deliverable:** Çalışan auth akışı, protected route sistemi

---

### Faz 2 — Ana Sayfa & Temel UI Bileşenleri
**Tahmini Süre:** 3-4 gün

**Hedefler:**
- [ ] Atomik UI bileşenleri: `Button`, `Input`, `Badge`, `Modal`, `Spinner`, `EmptyState`
- [ ] `StarRating` bileşeni
- [ ] **HomePage** — Hero section (statik içerik + animasyon)
- [ ] **RouteCard** bileşeni
- [ ] Öne çıkan rotalar bölümü (mock data veya API'den ilk 6)
- [ ] Kategori vitrin bölümü
- [ ] İstatistik bantı (sayaç animasyonu)
- [ ] Framer Motion `fadeUp` ve `staggerContainer` animasyonları
- [ ] Responsive tasarım (mobile-first, sm/md/lg breakpoints)

**Deliverable:** Görsel olarak tamamlanmış ana sayfa

---

### Faz 3 — Keşfet & Harita Ekranı
**Tahmini Süre:** 4-5 gün

**Hedefler:**
- [ ] React-Leaflet kurulumu + `KulturoMap` wrapper bileşeni
- [ ] CartoDB Voyager tile entegrasyonu
- [ ] `CategoryMarker` — özel SVG pin bileşenleri
- [ ] `MarkerClusterGroup` entegrasyonu
- [ ] **ExplorePage** layout (split panel)
- [ ] Mekan listesi + `PlaceCard` bileşeni
- [ ] `BoundsListener` — harita kaydırınca filtre güncelleme
- [ ] Filtre paneli (arama, kategori, UNESCO toggle)
- [ ] `PlaceDetailPanel` — Framer Motion `mapPanelSlide`
- [ ] "Benim konumum" butonu (Geolocation API + nearby endpoint)
- [ ] `placeService` entegrasyonu + React Query hooks

**Deliverable:** Tam işlevsel harita + mekan keşif ekranı

---

### Faz 4 — Rota Oluşturucu (Core Feature)
**Tahmini Süre:** 5-6 gün

**Hedefler:**
- [ ] `routeBuilderStore` Zustand store kurulumu
- [ ] **RouteBuilderPage** üç bölge layout
- [ ] Rota bilgisi formu (React Hook Form + Zod)
- [ ] Mekan arama + `PlaceRow` bileşeni
- [ ] Stop listesi → `@dnd-kit/sortable` entegrasyonu
- [ ] `RouteStopItem` bileşeni (sürükle, not, süre)
- [ ] `RoutePolyline` + `RouteStopMarker` harita bileşenleri
- [ ] Harita üzerinde tıklama → nearby mekan arama
- [ ] "Taslak kaydet" akışı (POST routes → POST stops)
- [ ] "Yayınla" akışı (PUT routes `is_public: true`)
- [ ] Sayfa terk uyarısı (`useBeforeUnload` hook)
- [ ] Düzenleme modu (`/rota/:id/duzenle`)

**Deliverable:** Tam işlevsel rota oluşturucu

---

### Faz 5 — Rota Detay & Sosyal Özellikler
**Tahmini Süre:** 3-4 gün

**Hedefler:**
- [ ] **RouteDetailPage** — kapak banner, durak listesi, harita
- [ ] `RouteLikeButton` — animasyonlu beğeni bileşeni
- [ ] Like/unlike API entegrasyonu (optimistic update)
- [ ] Yorum bölümü — `ReviewForm` + `ReviewList`
- [ ] `reviewService` entegrasyonu
- [ ] Rota paylaşma (Web Share API + kopyala butonu)
- [ ] "Rotayı Kopyala" özelliği (clone functionality, ileriki faz)
- [ ] **MyRoutesPage** — sekme bazlı kendi rota listesi

**Deliverable:** Eksiksiz sosyal rota detay deneyimi

---

### Faz 6 — Profil, KVKK & Cila
**Tahmini Süre:** 2-3 gün

**Hedefler:**
- [ ] **ProfilePage** — profil güncelleme formu
- [ ] Veri dışa aktarma butonu (`GET /users/me/export-data`)
- [ ] Hesap silme akışı (onay metni modal)
- [ ] **NotFoundPage** — özel 404 tasarımı
- [ ] Meta tag / Open Graph optimizasyonu (`react-helmet-async`)
- [ ] Loading skeleton bileşenleri (kart, harita, detay paneli)
- [ ] Error boundary bileşeni
- [ ] OSM ODbL attribution zorunluluğu (footer + harita)
- [ ] Lighthouse audit ve performans iyileştirmeleri

**Deliverable:** Production-ready, KVKK uyumlu uygulama

---

## 11. Performans & Erişilebilirlik Standartları

### 11.1 Performans Hedefleri (Lighthouse)
| Metrik | Hedef |
|---|---|
| LCP (Largest Contentful Paint) | < 2.5s |
| FID / INP | < 100ms |
| CLS | < 0.1 |
| Lighthouse Performance Score | ≥ 85 |
| Bundle Size (gzip) | < 300KB (initial) |

### 11.2 Optimizasyon Teknikleri
- **Code Splitting:** `React.lazy` + `Suspense` — harita, rota builder ayrı chunk
- **Image Lazy Loading:** `loading="lazy"` + Intersection Observer
- **React Query Cache:** 5 dakika stale time → gereksiz API çağrısı önleme
- **Marker Clustering:** 100+ pin → performanslı render
- **Debounce:** Arama inputları 300-400ms
- **Virtualization:** 50+ stop listesi için `@tanstack/react-virtual`

### 11.3 Erişilebilirlik (a11y)
- Tüm etkileşimli elementler `aria-label` veya anlamlı metin içerir
- Klavye navigasyonu: Tab sırası, Enter/Space tetikleyici, Escape modal kapat
- Renk kontrastı: WCAG AA minimum (4.5:1 metin)
- `prefers-reduced-motion` media query → animasyonları kısalt
- Harita: Mekan listesi klavye erişilebilir alternatif (harita tek başına yeterli değil)
- Form hataları: `aria-describedby` ile hata mesajına bağlantı

---

## 12. Test Stratejisi

### 12.1 Test Katmanları

**Birim Testler (Vitest + Testing Library):**
- Validasyon fonksiyonları (18+ kontrolü, KVKK zorunluluğu)
- Zustand store action'ları (login, logout, token refresh)
- Yardımcı fonksiyonlar (koordinat formatı, süre dönüşümü)

**Entegrasyon Testleri:**
- Auth akışı (login → token store → korumalı rota erişimi)
- Rota oluşturma (form → POST route → POST stop'lar)
- Beğeni akışı (idempotent davranış)
- Form validasyon hata durumları

**E2E Testler (Playwright — opsiyonel, Faz 6+):**
- Kayıt ve giriş akışı
- Mekan arama ve filtreleme
- Rota oluştur → yayınla → görüntüle tam akışı

### 12.2 Mock Stratejisi
- `msw` (Mock Service Worker) — API endpoint'lerini development'ta mockla
- Fixture dosyaları: `src/__fixtures__/place.js`, `route.js`, `user.js`

---

## Ekler

### Ek A: Ortam Değişkenleri (`.env.example`)
```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_MAP_DEFAULT_LAT=39.0
VITE_MAP_DEFAULT_LNG=35.0
VITE_MAP_DEFAULT_ZOOM=6
VITE_APP_NAME=KültürRota
```

### Ek B: Kategori Renk Haritası
```js
// src/constants/categories.js
export const CATEGORY_CONFIG = {
  museum:               { label: 'Müze',          color: '#2A9D8F', icon: 'Building2'  },
  archaeological_site:  { label: 'Arkeolojik Alan',color: '#D4883A', icon: 'Landmark'  },
  mosque:               { label: 'Cami',           color: '#264653', icon: 'Moon'       },
  palace:               { label: 'Saray',          color: '#A0522D', icon: 'Crown'      },
  historic:             { label: 'Tarihi Alan',    color: '#6B5B4E', icon: 'MapPin'    },
  church:               { label: 'Kilise',         color: '#9E8E7E', icon: 'Church'    },
  archaeological_park:  { label: 'Ark. Park',      color: '#E76F51', icon: 'Trees'     },
};
```

### Ek C: ODbL Attribution Zorunluluğu
PRD §20 uyarınca tüm harita görünümlerinde ve mekan listelerinde şu attribution görünmelidir:
```
© OpenStreetMap katkıcıları | Veriler ODbL lisansı altında
```
Footer'da ve Leaflet attribution kontrolünde yer almalıdır.

---

*Bu belge KültürRota projesi için yaşayan bir referans dokümandır. Her faz tamamlandıkça ilgili bölümler güncellenmelidir.*