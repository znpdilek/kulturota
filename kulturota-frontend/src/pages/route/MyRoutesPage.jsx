import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Map, MapPin, Calendar, Loader2 } from 'lucide-react';
import { routeService } from '../../services/routeService';
import { Link } from 'react-router-dom'; // Bunu ekle

const MyRoutesPage = () => {
  // Backend'den kullanıcının rotalarını çekiyoruz
  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['myRoutes'],
    queryFn: () => routeService.list()
  });

  // Gelen veriyi güvenli bir diziye (array) çeviriyoruz
  let safeRoutes = [];
  if (response?.data) {
    safeRoutes = Array.isArray(response.data) ? response.data : 
                 Array.isArray(response.data.items) ? response.data.items : [];
  }

  // 🕵️‍♂️ AJANIMIZ BURADA: FastAPI listeleme için bize tam olarak hangi isimleri gönderiyor?
  console.log("🕵️‍♂️ GELEN ROTA VERİSİ:", safeRoutes);
  if (response?.data) {
    safeRoutes = Array.isArray(response.data) ? response.data : 
                 Array.isArray(response.data.items) ? response.data.items : [];
  }

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-stone-100 p-8">
      <div className="max-w-6xl mx-auto">
        
        <div className="mb-8">
          <h1 className="font-display text-4xl text-sienna mb-2">Rotalarım</h1>
          <p className="font-ui text-stone-600">
            Kaydettiğiniz tüm kültürel miras rotaları burada listelenmektedir.
          </p>
        </div>

        {/* Yükleniyor Durumu */}
        {isLoading && (
          <div className="flex justify-center items-center py-20 text-sienna">
            <Loader2 className="w-10 h-10 animate-spin" />
          </div>
        )}

        {/* Hata Durumu */}
        {isError && (
          <div className="bg-rose-rug/10 border border-rose-rug text-rose-rug p-4 rounded-card font-ui text-center">
            Rotalarınız yüklenirken bir sorun oluştu.
          </div>
        )}

        {/* Boş Durum (Hiç rota yoksa) */}
        {!isLoading && !isError && safeRoutes.length === 0 && (
          <div className="bg-white p-12 rounded-organic shadow-sm border border-stone-200 text-center flex flex-col items-center">
            <div className="w-16 h-16 bg-stone-100 rounded-full flex items-center justify-center text-stone-400 mb-4">
              <Map size={32} />
            </div>
            <h3 className="font-ui text-lg font-semibold text-stone-800 mb-2">Henüz Rota Oluşturmadınız</h3>
            <p className="font-ui text-stone-500 max-w-md">
              Keşfet sayfasından mekanları bulabilir veya Rota Oluştur sayfasından ilk rotanızı çizebilirsiniz.
            </p>
          </div>
        )}

        {/* Rota Kartları Izgarası */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {!isLoading && safeRoutes.map((route) => (
            <Link to={`/rotalar/${route.id}`} key={route.id} className="bg-white rounded-card overflow-hidden shadow-card border border-stone-100 hover:border-amber transition-all group flex flex-col cursor-pointer hover:shadow-lg">
              
              {/* Kart Üst Görsel/Renk Alanı */}
              <div className="h-32 bg-sand relative flex items-center justify-center border-b border-stone-100">
                <Map className="w-12 h-12 text-sienna opacity-20 group-hover:scale-110 transition-transform" />
                {route.is_public && (
                  <span className="absolute top-3 right-3 bg-white px-2 py-1 rounded text-xs font-ui font-semibold text-turquoise shadow-sm">
                    Herkese Açık
                  </span>
                )}
              </div>

              {/* Kart İçeriği */}
              <div className="p-5 flex-grow flex flex-col">
                <h3 className="font-display text-xl text-stone-800 mb-3 line-clamp-1 group-hover:text-sienna transition-colors">
                  {route.title}
                </h3>
                
                <div className="space-y-2 mt-auto">
                  <div className="flex items-center gap-2 text-sm font-ui text-stone-600">
                    <MapPin size={16} className="text-stone-400" />
                    <span>{route.stop_count || 0} Mekan (Durak)</span>
                  </div>
                  
                  <div className="flex items-center gap-2 text-sm font-ui text-stone-600">
                    <Calendar size={16} className="text-stone-400" />
                    <span>Oluşturulma: {new Date(route.created_at || Date.now()).toLocaleDateString('tr-TR')}</span>
                  </div>
                </div>
              </div>
            </Link>  
          ))}
        </div>

      </div>
    </div>
  );
};

export default MyRoutesPage;