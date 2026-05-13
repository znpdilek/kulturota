import React, { useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { useQuery } from '@tanstack/react-query';
import { Search, MapPin, Plus, Trash2, Save, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';

import { placeService } from '../../services/placeService';
import { routeService } from '../../services/routeService';
import { useRouteStore } from '../../store/routeStore';
import { getCategoryConfig } from '../../constants/categories';
import L from 'leaflet';

const center = [38.4237, 27.1428];

const createCustomIcon = (rawCategory) => {
  const config = getCategoryConfig(rawCategory);
  return L.divIcon({
    className: 'bg-transparent border-0',
    html: `<div style="background-color: ${config.color}; width: 20px; height: 20px; border-radius: 50% 50% 50% 0; transform: rotate(-45deg); border: 2px solid white; box-shadow: 2px 2px 4px rgba(0,0,0,0.3);"></div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 20],
  });
};

const RouteBuilderPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [routeName, setRouteName] = useState(''); // Yeni: Rota adı için state
  const [isSaving, setIsSaving] = useState(false); // Yeni: Kaydediliyor durumu
  
  const { routeStops, addStop, removeStop, clearRoute } = useRouteStore();

  const { data: response, isLoading } = useQuery({
    queryKey: ['places', { q: searchQuery }],
    queryFn: () => placeService.list({ q: searchQuery || undefined })
  });

  let safePlaces = [];
  if (response?.data) {
    safePlaces = Array.isArray(response.data) ? response.data : 
                 Array.isArray(response.data.items) ? response.data.items : 
                 Array.isArray(response.data.data) ? response.data.data : [];
  }

  const routeCoordinates = routeStops.map(place => {
    const lat = place.koordinat?.enlem || place.koordinat?.lat || place.lat || place.latitude;
    const lng = place.koordinat?.boylam || place.koordinat?.lng || place.lng || place.longitude;
    return [lat, lng];
  }).filter(coord => coord[0] && coord[1]);

  // YENİ: Kaydetme Fonksiyonu
  const handleSaveRoute = async () => {
    if (!routeName.trim()) {
      toast.error('Lütfen rotanıza bir isim verin!');
      return;
    }

    try {
      setIsSaving(true);
      
      // 1. AŞAMA: Sadece Swagger'ın izin verdiği bilgileri gönderip boş rotayı oluşturuyoruz
      const routePayload = {
        title: routeName,
        is_public: false
      };

      const routeResponse = await routeService.create(routePayload);
      const newRouteId = routeResponse.data.id; // Backend'in bize verdiği yeni rotanın kimliği
      
      // 2. AŞAMA: Oluşan bu yeni rotaya sepetimizdeki mekanları tek tek durak (stop) olarak ekliyoruz
      for (let i = 0; i < routeStops.length; i++) {
        await routeService.addStop(newRouteId, {
          place_id: routeStops[i].id
        });
      }
      
      toast.success('Harika! Rotanız başarıyla kaydedildi.');
      clearRoute();
      setRouteName('');
    } catch (error) {
      console.error("🕵️‍♂️ BACKEND'DEN GELEN KAYIT HATASI:", error.response?.data);
      toast.error('Kaydedilemedi. Lütfen F12 Console sekmesine bakın.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-5rem)] bg-stone-100">
      
      <div className="w-[400px] bg-cream border-r border-stone-200 flex flex-col shadow-map-control z-20 shrink-0">
        
        <div className="p-6 border-b border-stone-200 bg-sand/30 flex flex-col max-h-[50vh]">
          <div className="flex justify-between items-center mb-4 shrink-0">
            <h2 className="font-display text-2xl text-sienna">Yeni Rotam</h2>
            {routeStops.length > 0 && (
              <button onClick={clearRoute} className="text-ui-xs font-ui text-rose-rug hover:underline flex items-center gap-1">
                <Trash2 size={14} /> Temizle
              </button>
            )}
          </div>

          {routeStops.length === 0 ? (
            <p className="text-stone-500 font-ui text-sm italic shrink-0">Henüz rotanıza mekan eklemediniz. Aşağıdan mekan seçin.</p>
          ) : (
            <div className="space-y-2 overflow-y-auto pr-2 scrollbar-hide mb-4 flex-grow">
              {routeStops.map((stop, index) => {
                const placeName = typeof stop.isim === 'object' ? (stop.isim?.tr || stop.isim?.en) : (stop.isim || stop.name);
                return (
                  <div key={stop.id} className="flex justify-between items-center bg-white p-3 rounded-card shadow-sm border border-stone-100 shrink-0">
                    <div className="flex items-center gap-3">
                      <div className="w-6 h-6 rounded-full bg-sienna text-white flex items-center justify-center font-ui text-xs font-bold shrink-0">
                        {index + 1}
                      </div>
                      <span className="font-ui text-sm font-medium text-stone-800 line-clamp-1">{placeName}</span>
                    </div>
                    <button onClick={() => removeStop(stop.id)} className="text-stone-400 hover:text-rose-rug transition-colors shrink-0 ml-2">
                      <Trash2 size={16} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {routeStops.length > 1 && (
            <div className="shrink-0 pt-2 border-t border-stone-200/50 mt-auto">
              <input 
                type="text" 
                placeholder="Örn: Ege Tarih Turu" 
                value={routeName}
                onChange={(e) => setRouteName(e.target.value)}
                className="w-full bg-white border border-stone-200 py-2 px-3 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber text-sm font-ui mb-3"
              />
              <button 
                onClick={handleSaveRoute}
                disabled={isSaving}
                className="w-full bg-sienna text-white py-3 rounded-organic font-ui font-semibold shadow-card hover:bg-amber transition-all flex justify-center items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save size={18} />}
                {isSaving ? 'Kaydediliyor...' : 'Rotayı Kaydet'}
              </button>
            </div>
          )}
        </div>

        <div className="p-6 flex flex-col flex-grow overflow-hidden">
          <h3 className="font-ui font-semibold text-stone-700 mb-3">Mekan Ekle</h3>
          <div className="relative mb-4">
            <input 
              type="text" 
              placeholder="Mekan ara..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-stone-200 py-2.5 pl-9 pr-4 rounded-card focus:outline-none focus:ring-2 focus:ring-amber/20 focus:border-amber text-sm font-ui"
            />
            <Search className="absolute left-3 top-3 text-stone-400 w-4 h-4" />
          </div>

          <div className="flex-grow overflow-y-auto pr-2">
            {isLoading && <div className="flex justify-center p-4"><Loader2 className="w-6 h-6 animate-spin text-sienna" /></div>}
            
            {!isLoading && safePlaces.map(place => {
              const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en) : (place.isim || place.name);
              const isAdded = routeStops.some(stop => stop.id === place.id);

              return (
                <div key={place.id} className="flex justify-between items-center p-3 mb-2 bg-white rounded-card border border-stone-100 hover:border-amber transition-all group shrink-0">
                  <div className="pr-2">
                    <h4 className="font-ui text-sm font-medium text-stone-800 group-hover:text-sienna line-clamp-1">{placeName}</h4>
                    <p className="font-ui text-xs text-stone-500 flex items-center gap-1 mt-0.5">
                      <MapPin size={12} /> {place.sehir || place.city || 'Konum Belirtilmemiş'}
                    </p>
                  </div>
                  <button 
                    onClick={() => isAdded ? removeStop(place.id) : addStop(place)}
                    className={`p-2 rounded-full transition-colors shrink-0 ${isAdded ? 'bg-turquoise/10 text-turquoise' : 'bg-stone-100 text-stone-500 hover:bg-sienna hover:text-white'}`}
                    title={isAdded ? "Rotadan Çıkar" : "Rotaya Ekle"}
                  >
                    {isAdded ? <Trash2 size={16} /> : <Plus size={16} />}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

      </div>

      <div className="flex-grow relative z-0">
        <MapContainer center={center} zoom={8} className="w-full h-full" zoomControl={false}>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
          />
          
          {!isLoading && safePlaces.map((place) => {
            let lat = place.koordinat?.enlem || place.koordinat?.lat || place.lat || place.latitude;
            let lng = place.koordinat?.boylam || place.koordinat?.lng || place.lng || place.longitude;
            if (!lat || !lng) return null;

            const rawCategory = Array.isArray(place.kategori) && place.kategori.length > 0 ? place.kategori[0] : (place.kategori || place.category);
            const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en) : (place.isim || place.name);

            return (
              <Marker key={`builder-marker-${place.id}`} position={[lat, lng]} icon={createCustomIcon(rawCategory)}>
                <Popup className="font-ui text-sm">
                  <strong>{placeName}</strong>
                </Popup>
              </Marker>
            );
          })}

          {routeCoordinates.length > 1 && (
            <Polyline 
              positions={routeCoordinates} 
              pathOptions={{ color: '#A0522D', weight: 3, dashArray: '8, 8', opacity: 0.8 }} 
            />
          )}
        </MapContainer>
      </div>
    </div>
  );
};

export default RouteBuilderPage;