import React, { useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, MapPin, Star, MessageSquare, Loader2, Send, Camera, ImagePlus } from 'lucide-react';
import toast from 'react-hot-toast';
import { placeService } from '../../services/placeService';

const PlaceDetailPage = () => {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);
  
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');

  // 1. Veri Çekme İşlemleri
  const { data: placeData, isLoading: isPlaceLoading } = useQuery({
    queryKey: ['placeDetail', id],
    queryFn: () => placeService.detail(id)
  });

  const { data: reviewsData, isLoading: isReviewsLoading } = useQuery({
    queryKey: ['placeReviews', id],
    queryFn: () => placeService.getReviews(id)
  });

  // 2. Yorum Gönderme (Mutation)
  const submitReview = useMutation({
    mutationFn: (newReview) => placeService.addReview(id, newReview),
    onSuccess: () => {
      toast.success('Yorumunuz başarıyla eklendi!');
      setComment('');
      setRating(5);
      queryClient.invalidateQueries(['placeReviews', id]);
    },
    onError: (error) => {
      toast.error('Yorum eklenemedi. Belki bu mekana zaten yorum yaptınız?');
    }
  });

  // 3. Fotoğraf Yükleme (Mutation)
  const uploadPhotoMutation = useMutation({
    mutationFn: (formData) => placeService.uploadPhoto(formData),
    onSuccess: () => {
      toast.success('Fotoğraf yüklendi! Moderasyon onayından sonra yayınlanacaktır.');
    },
    onError: (error) => {
      const status = error.response?.status;
      if (status === 413) {
        toast.error('Dosya çok büyük. Maksimum 5MB yükleyebilirsiniz.');
      } else if (status === 415) {
        toast.error('Geçersiz format. Sadece JPG veya PNG yükleyebilirsiniz.');
      } else {
        toast.error('Fotoğraf yüklenirken bir sorun oluştu.');
      }
    }
  });

  if (isPlaceLoading) return <div className="flex h-screen items-center justify-center"><Loader2 className="w-10 h-10 animate-spin text-sienna" /></div>;

  const place = placeData?.data;
  if (!place) return <div className="p-10 text-center">Mekan bulunamadı.</div>;

  const placeName = typeof place.isim === 'object' ? (place.isim?.tr || place.isim?.en) : (place.isim || place.name);
  const placeDesc = typeof place.aciklama === 'object' ? (place.aciklama?.tr || place.aciklama?.en) : (place.aciklama || place.description_tr || 'Bu mekan için henüz bir açıklama girilmemiş.');
  const reviews = Array.isArray(reviewsData?.data) ? reviewsData.data : Array.isArray(reviewsData?.data?.items) ? reviewsData.data.items : [];

  const handleReviewSubmit = (e) => {
    e.preventDefault();
    if (!comment.trim()) {
      toast.error('Lütfen bir yorum yazın.');
      return;
    }
    const reviewPayload = {
      rating: rating,
      body: comment,
      visited_at: new Date().toISOString().split('T')[0]
    };
    submitReview.mutate(reviewPayload);
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('place_id', id);
    formData.append('file', file);

    uploadPhotoMutation.mutate(formData);
    e.target.value = null; // Aynı dosyayı tekrar seçebilmek için input'u sıfırla
  };

  return (
    <div className="min-h-screen bg-stone-100 p-6 md:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Üst Bilgi Kartı */}
        <div className="bg-white rounded-organic shadow-card overflow-hidden border border-stone-200">
          <div className="p-8">
            <Link to="/kesfet" className="inline-flex items-center gap-2 text-stone-500 hover:text-sienna mb-6 transition-colors font-ui">
              <ArrowLeft size={18} /> Keşfet'e Dön
            </Link>
            
            <div className="flex justify-between items-start mb-4">
              <h1 className="font-display text-4xl text-sienna">{placeName}</h1>
              
              {/* Fotoğraf Yükleme Butonu ve Gizli Input */}
              <input 
                type="file" 
                accept=".jpg,.jpeg,.png" 
                className="hidden" 
                ref={fileInputRef}
                onChange={handleFileChange}
              />
              <button 
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadPhotoMutation.isLoading}
                className="flex items-center gap-2 bg-stone-100 hover:bg-stone-200 text-stone-700 px-4 py-2 rounded-badge font-ui text-sm font-semibold transition-colors disabled:opacity-50"
              >
                {uploadPhotoMutation.isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera size={18} />}
                Fotoğraf Ekle
              </button>
            </div>
            
            <div className="flex flex-wrap gap-4 mb-6">
              <div className="flex items-center gap-2 text-stone-600 font-ui bg-stone-50 px-3 py-1.5 rounded-full border border-stone-100">
                <MapPin size={16} className="text-turquoise" />
                <span>{place.sehir || place.city || 'Konum Belirtilmemiş'}</span>
              </div>
            </div>

            <p className="font-ui text-stone-700 leading-relaxed text-lg whitespace-pre-line">
              {placeDesc}
            </p>
          </div>
        </div>

        {/* Yorumlar Bölümü */}
        <div className="bg-white rounded-organic shadow-card border border-stone-200 p-8">
          <h2 className="font-display text-2xl text-stone-800 mb-6 flex items-center gap-2">
            <MessageSquare className="text-sienna" /> Ziyaretçi Yorumları
          </h2>

          <form onSubmit={handleReviewSubmit} className="mb-10 bg-sand/20 p-6 rounded-card border border-stone-100">
            <h3 className="font-ui font-semibold text-stone-700 mb-3">Deneyiminizi Paylaşın</h3>
            
            <div className="flex items-center gap-2 mb-4">
              <span className="font-ui text-sm text-stone-600 mr-2">Puanınız:</span>
              {[1, 2, 3, 4, 5].map((star) => (
                <button 
                  key={star} 
                  type="button"
                  onClick={() => setRating(star)}
                  className={`transition-colors ${star <= rating ? 'text-amber' : 'text-stone-300 hover:text-amber/50'}`}
                >
                  <Star size={24} fill={star <= rating ? "currentColor" : "none"} />
                </button>
              ))}
            </div>

            <textarea 
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Bu mekan hakkında ne düşünüyorsunuz?"
              className="w-full bg-white border border-stone-200 rounded-card p-4 font-ui focus:outline-none focus:ring-2 focus:ring-amber/30 focus:border-amber resize-none h-24 mb-3"
            />
            
            <button 
              type="submit" 
              disabled={submitReview.isLoading}
              className="bg-sienna text-white px-6 py-2.5 rounded-badge font-ui font-semibold hover:bg-amber transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              {submitReview.isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send size={18} />}
              Yorumu Gönder
            </button>
          </form>

          {isReviewsLoading ? (
            <div className="flex justify-center p-6"><Loader2 className="w-6 h-6 animate-spin text-stone-400" /></div>
          ) : reviews.length === 0 ? (
            <p className="text-center font-ui text-stone-500 italic py-6">İlk yorumu yapan siz olun!</p>
          ) : (
            <div className="space-y-4">
              {reviews.map((review, idx) => {
                const userName = review?.author?.username || review?.user?.username || 'Gezgin';
                const userInitial = userName ? userName.charAt(0).toUpperCase() : 'G';
                const reviewText = String(review?.body || review?.comment || review?.text || 'Yorum içeriği yok.');
                const rating = Number(review?.rating) || 5;

                return (
                  <div key={review?.id || idx} className="border-b border-stone-100 pb-4 last:border-0">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-turquoise/20 text-turquoise flex items-center justify-center font-bold font-ui text-sm uppercase">
                          {userInitial}
                        </div>
                        <span className="font-ui font-semibold text-stone-700">{userName}</span>
                      </div>
                      <div className="flex text-amber">
                        {[...Array(5)].map((_, i) => (
                          <Star key={i} size={14} fill={i < rating ? "currentColor" : "none"} className={i >= rating ? "text-stone-200" : ""} />
                        ))}
                      </div>
                    </div>
                    <p className="font-ui text-stone-600 text-sm ml-10">{reviewText}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default PlaceDetailPage;