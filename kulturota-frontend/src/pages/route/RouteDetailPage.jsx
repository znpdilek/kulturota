import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowLeft, MapPin, Loader2, Calendar } from 'lucide-react';
import L from 'leaflet';
import { routeService } from '../../services/routeService';
import { getCategoryConfig } from '../../constants/categories';

const createCustomIcon = (rawCategory) => {
  const config = getCategoryConfig(rawCategory);
  return L.divIcon({
    className: 'bg-transparent border-0',
    html: `<div style="background-color: ${config.color}; width: 24px; height: 24px; border-radius: 50% 50% 50% 0; transform: rotate(-45deg); border: 2px solid white; box-shadow: 2px 2px 6px rgba(0,0,0,0.4);"></div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 24],
  });
};

const RouteDetailPage = () => {
  const { id } = useParams(); // URL'den rotanın ID'sini alıyoruz

  // Rotanın genel bilgilerini çek
  const { data: routeData, isLoading: isRouteLoading } = useQuery({
    queryKey: ['routeDetail', id],
    queryFn: () => routeService.detail(id)
  });

  // Rotanın içindeki durakları (mekanları) çek
  const { data: stopsData, isLoading: isStopsLoading } = useQuery({
    queryKey: ['routeStops', id],
    queryFn: () => routeService.getStops(id)
  });

  const route = routeData?.data;
  let stops = [];
  if (stopsData?.data) {
    stops = Array.isArray(stopsData.data) ? stopsData.data : 
            Array.isArray(stopsData.data.items) ? stopsData.data.items : [];
  }

  // Haritaya çizgi (Polyline) çekmek için koordinatları hazırlıyoruz
  const routeCoordinates = stops.map(stop => {
    const place = stop.place || stop; // Backend yapısına göre önlem
    const lat = place.koordinat?.enlem || place.koordinat?.lat || place.lat || place.latitude;
    const lng = place.koordinat?.boylam || place.koordinat?.lng || place.lng || place.longitude;
    return [lat, lng];
  }).filter(coord => coord[0] && coord[1]);

  const mapCenter = routeCoordinates.length > 0 ? routeCoordinates[0] : [38.4237, 27.1428];

  if (isRouteLoading || isStopsLoading) {
    return <div className="flex h-[calc(100vh-5rem)] items-center justify-center"><Loader2 className="w-10 h-10 animate-spin text-sienna" /></div>;
  }

  return (
    <div className="flex h-[calc(100vh-5rem)] bg-stone-100">
      
      {/* Sol Panel: Detaylar ve Mekan Listesi */}
      <div className="w-[400px] bg-cream border-r border-stone-200 flex flex-col shadow-map-control z-20 shrink-0">
        
        {/* Üst Kısım: Rota Bilgileri */}
        <div className="p-6 border-b border-stone-200 bg-sand/30">
          <Link to="/rotalarim" className="inline-flex items-center gap-2 text-stone-500 hover:text-sienna mb-4 transition-colors font-ui text-sm">
            <ArrowLeft size={16} /> Rotalarıma Dön
          </Link>
          <h2 className="font-display text-3xl text-sienna mb-2">{route?.title || 'İsimsiz Rota'}</h2>
          
          <div className="space-y-2 mt-4">
            <div className="flex items-center gap-2 text-sm font-ui text-stone-600">
              <MapPin size={16} className="text-turquoise" />
              <span>{stops.length} Mekan (Durak)</span>
            </div>
            <div className="flex items-center gap-2 text-sm font-ui text-stone-600">
              <Calendar size={16} className="text-amber" />
              <span>{new Date(route?.created_at || Date.now()).toLocaleDateString('tr-TR')}</span>
            </div>
          </div>
        </div>

        {/* Alt Kısım: Durak Listesi */}
        <div className="p-6 flex flex-col flex-grow overflow-hidden">
          <h3 className="font-ui font-semibold text-stone-700 mb-4">Rota Güzergahı</h3>
          
          <div className="flex-grow overflow-y-auto pr-2 space-y-3 scrollbar-hide">
            {stops.length === 0 ? (
              <p className="text-sm font-ui text-stone-500 italic">Bu rotada henüz mekan yok.</p>
            ) : (
              stops.map((stop, index) => {
                const place = stop.place || stop;
                const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en) : (place.isim || place.name);
                
                return (
                  <div key={stop.id || index} className="flex items-center p-3 bg-white rounded-card border border-stone-100 shadow-sm">
                    <div className="w-8 h-8 rounded-full bg-sienna text-white flex items-center justify-center font-ui text-sm font-bold shrink-0 mr-3 shadow-md">
                      {index + 1}
                    </div>
                    <div>
                      <h4 className="font-ui text-sm font-medium text-stone-800 line-clamp-1">{placeName}</h4>
                      <p className="font-ui text-xs text-stone-500 mt-0.5">{place.sehir || place.city || 'Konum Belirtilmemiş'}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Sağ Panel: Harita */}
      <div className="flex-grow relative z-0">
        <MapContainer center={mapCenter} zoom={10} className="w-full h-full" zoomControl={false}>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
          />
          
          {stops.map((stop, index) => {
            const place = stop.place || stop;
            const lat = place.koordinat?.enlem || place.koordinat?.lat || place.lat || place.latitude;
            const lng = place.koordinat?.boylam || place.koordinat?.lng || place.lng || place.longitude;
            
            if (!lat || !lng) return null;

            const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en) : (place.isim || place.name);
            const rawCategory = Array.isArray(place.kategori) && place.kategori.length > 0 ? place.kategori[0] : (place.kategori || place.category);

            return (
              <Marker key={`detail-marker-${index}`} position={[lat, lng]} icon={createCustomIcon(rawCategory)}>
                <Popup className="font-ui text-sm">
                  <strong>{index + 1}. {placeName}</strong>
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

export default RouteDetailPage;