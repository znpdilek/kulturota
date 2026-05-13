import React, { useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Search, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { placeService } from '../../services/placeService';
import PlaceCard from '../../components/place/PlaceCard';
import { getCategoryConfig } from '../../constants/categories';
import { Link } from 'react-router-dom';

// PRD §2 D1 — pilot şehir İzmir. Harita merkezi + sıkı bbox burada belirlenir.
const IZMIR_CENTER = [38.42, 27.14];
const IZMIR_BOUNDS = L.latLngBounds(L.latLng(37.78, 26.10), L.latLng(39.18, 28.42));
const IZMIR_BBOX_PARAM = '26.10,37.78,28.42,39.18';

const CATEGORIES = [
  { id: 'all', label: 'Tümü' },
  { id: 'museum', label: 'Müze' },
  { id: 'archaeological_site', label: 'Arkeolojik Alan' },
  { id: 'ancient_city', label: 'Antik Kent' },
  { id: 'mosque', label: 'Cami' },
  { id: 'church', label: 'Kilise' },
  { id: 'synagogue', label: 'Sinagog' },
  { id: 'palace', label: 'Saray' },
  { id: 'castle', label: 'Kale' },
  { id: 'tower', label: 'Kule' },
  { id: 'monument', label: 'Anıt' },
  { id: 'fountain', label: 'Çeşme' },
  { id: 'aqueduct', label: 'Su Kemeri' },
  { id: 'bath', label: 'Hamam' },
  { id: 'caravanserai', label: 'Kervansaray' },
  { id: 'theatre', label: 'Tiyatro' },
  { id: 'agora', label: 'Agora' },
  { id: 'library', label: 'Kütüphane' },
  { id: 'ruins', label: 'Ören Yeri' },
  { id: 'historic_site', label: 'Tarihi Alan' },
];

const createCustomIcon = (rawCategory) => {
  const config = getCategoryConfig(rawCategory);
  return L.divIcon({
    className: 'bg-transparent border-0',
    html: `
      <div style="
        background-color: ${config.color};
        width: 24px;
        height: 24px;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        border: 2px solid white;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.4);
      "></div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 24],
    popupAnchor: [0, -24],
  });
};

const resolvePlaceName = (place) => {
  if (!place) return 'İsimsiz Mekan';
  if (typeof place.isim === 'object') return place.isim?.tr || place.isim?.en || 'İsimsiz Mekan';
  return place.isim || place.name || 'İsimsiz Mekan';
};

const ExplorePage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [isUnescoOnly, setIsUnescoOnly] = useState(false);
  const [isPanelOpen, setIsPanelOpen] = useState(true);

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['places', { category: selectedCategory, unesco: isUnescoOnly, q: searchQuery }],
    queryFn: () =>
      placeService.list({
        // "Tümü" filtresi: backend max limit (500) ile mekanları getir;
        // her kategori değişiminde aynı limit kullanılır.
        limit: 500,
        bbox: IZMIR_BBOX_PARAM,
        category: selectedCategory === 'all' ? undefined : selectedCategory,
        unesco: isUnescoOnly ? true : undefined,
        q: searchQuery || undefined,
      }),
  });

  let extractedPlaces = [];
  if (response?.data) {
    if (Array.isArray(response.data)) {
      extractedPlaces = response.data;
    } else if (Array.isArray(response.data.items)) {
      extractedPlaces = response.data.items;
    } else if (Array.isArray(response.data.data)) {
      extractedPlaces = response.data.data;
    }
  }

  const safePlaces = Array.isArray(extractedPlaces) ? extractedPlaces : [];

  return (
    <div className="flex h-[calc(100vh-5rem)] relative overflow-hidden bg-stone-100">
      <div
        className={`bg-cream border-r border-stone-200 flex flex-col shadow-map-control z-20 transition-all duration-300 ease-in-out shrink-0 w-[380px] ${
          isPanelOpen ? 'ml-0' : '-ml-[380px]'
        }`}
      >
        <div className="p-6 border-b border-stone-200">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="font-display text-display-lg text-sienna">Keşfet</h2>
            <span className="font-ui text-xs text-stone-500">
              {isLoading ? '...' : `${safePlaces.length} mekan`}
            </span>
          </div>

          <div className="relative mb-4">
            <input
              type="text"
              placeholder="Mekan veya rota ara..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-stone-200 py-3 pl-10 pr-4 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber transition-all font-ui text-ui-sm"
            />
            <Search className="absolute left-3 top-3.5 text-stone-400 w-5 h-5" />
          </div>

          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide mb-4">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`whitespace-nowrap px-4 py-1.5 rounded-badge font-ui text-sm transition-all border ${
                  selectedCategory === cat.id
                    ? 'bg-sienna text-white border-sienna shadow-card'
                    : 'bg-white text-stone-600 border-stone-200 hover:border-amber'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 cursor-pointer w-max">
            <input
              type="checkbox"
              checked={isUnescoOnly}
              onChange={(e) => setIsUnescoOnly(e.target.checked)}
              className="w-4 h-4 text-turquoise border-stone-300 rounded focus:ring-turquoise"
            />
            <span className="font-ui text-sm text-stone-700">Sadece UNESCO Mirasları</span>
          </label>
        </div>

        <div className="flex-grow overflow-y-auto p-6 bg-stone-50/50">
          {isLoading && (
            <div className="flex justify-center items-center h-full text-sienna">
              <Loader2 className="w-8 h-8 animate-spin" />
            </div>
          )}

          {isError && (
            <p className="text-rose-rug font-ui text-sm text-center mt-4">
              Mekanlar yüklenirken bir hata oluştu.
            </p>
          )}

          {!isLoading && !isError && safePlaces.length === 0 && (
            <p className="text-stone-500 font-ui text-sm text-center mt-4">
              Bu filtrelerle eşleşen mekan bulunamadı.
            </p>
          )}

          {!isLoading &&
            safePlaces.map((place, index) => (
              <Link
                key={`card-wrapper-${place?.id || index}`}
                to={`/mekanlar/${place.id}`}
                className="block mb-4 focus:outline-none focus:ring-2 focus:ring-amber/30 rounded-card"
              >
                <PlaceCard place={place || {}} />
              </Link>
            ))}
        </div>
      </div>

      <button
        onClick={() => setIsPanelOpen(!isPanelOpen)}
        className={`absolute top-1/2 -translate-y-1/2 z-30 bg-white p-2 rounded-r-lg shadow-md border border-stone-200 border-l-0 text-stone-600 hover:text-sienna transition-all duration-300 ${
          isPanelOpen ? 'left-[380px]' : 'left-0'
        }`}
      >
        {isPanelOpen ? <ChevronLeft size={24} /> : <ChevronRight size={24} />}
      </button>

      <div className="flex-grow relative z-0 w-full h-full">
        <MapContainer
          center={IZMIR_CENTER}
          zoom={9}
          minZoom={8}
          maxZoom={18}
          maxBounds={IZMIR_BOUNDS}
          maxBoundsViscosity={0.8}
          className="w-full h-full"
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
          />

          {!isLoading &&
            safePlaces.map((place, index) => {
              if (!place) return null;

              let lat;
              let lng;
              if (place.koordinat) {
                lat = place.koordinat.enlem || place.koordinat.lat || place.koordinat.latitude;
                lng = place.koordinat.boylam || place.koordinat.lng || place.koordinat.longitude;
              } else {
                lat = place.lat || place.latitude || place.enlem;
                lng = place.lng || place.longitude || place.boylam;
              }

              if (!lat || !lng) return null;

              const placeName = resolvePlaceName(place);
              const rawCategory =
                Array.isArray(place.kategori) && place.kategori.length > 0
                  ? place.kategori[0]
                  : place.kategori || place.category;

              return (
                <Marker
                  key={`marker-${place.id || index}`}
                  position={[lat, lng]}
                  icon={createCustomIcon(rawCategory)}
                >
                  <Popup className="font-ui">
                    <span className="font-semibold text-sienna">{placeName}</span>
                    <br />
                    {place.sehir || place.il || place.city || 'İzmir'}
                    <br />
                    <Link
                      to={`/mekanlar/${place.id}`}
                      className="text-amber font-semibold underline text-xs"
                    >
                      Detayları gör →
                    </Link>
                  </Popup>
                </Marker>
              );
            })}
        </MapContainer>
      </div>
    </div>
  );
};

export default ExplorePage;
