import React, { useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  MapPin,
  Star,
  MessageSquare,
  Loader2,
  Send,
  ImagePlus,
  X,
  Camera,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { placeService } from '../../services/placeService';
import { getCategoryConfig } from '../../constants/categories';

const resolvePlaceName = (place) => {
  if (!place) return 'İsimsiz Mekan';
  if (typeof place.isim === 'object') return place.isim?.tr || place.isim?.en || 'İsimsiz Mekan';
  return place.isim || place.name || 'İsimsiz Mekan';
};

const resolveDescription = (place) => {
  if (!place) return null;
  if (typeof place.aciklama === 'object') return place.aciklama?.tr || place.aciklama?.en || null;
  return place.aciklama || place.description_tr || null;
};

const PlaceDetailPage = () => {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);

  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);

  const { data: placeData, isLoading: isPlaceLoading } = useQuery({
    queryKey: ['placeDetail', id],
    queryFn: () => placeService.detail(id),
  });

  const { data: reviewsData, isLoading: isReviewsLoading } = useQuery({
    queryKey: ['placeReviews', id],
    queryFn: () => placeService.getReviews(id),
  });

  const { data: photosData, isLoading: isPhotosLoading } = useQuery({
    queryKey: ['placePhotos', id],
    queryFn: () => placeService.getPhotos(id),
  });

  if (isPlaceLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="w-10 h-10 animate-spin text-sienna" />
      </div>
    );
  }

  const place = placeData?.data;
  if (!place) return <div className="p-10 text-center font-ui text-stone-600">Mekan bulunamadı.</div>;

  const placeName = resolvePlaceName(place);
  const placeDesc = resolveDescription(place) || 'Bu mekan için henüz bir açıklama girilmemiş.';
  const rawCategory =
    Array.isArray(place.kategori) && place.kategori.length > 0
      ? place.kategori[0]
      : place.kategori || place.category;
  const categoryConfig = getCategoryConfig(rawCategory);

  const reviewsRaw = reviewsData?.data;
  const reviews = Array.isArray(reviewsRaw)
    ? reviewsRaw
    : Array.isArray(reviewsRaw?.items)
    ? reviewsRaw.items
    : [];
  const aggregate = reviewsRaw?.aggregate || null;

  const photosRaw = photosData?.data;
  const photos = Array.isArray(photosRaw)
    ? photosRaw
    : Array.isArray(photosRaw?.items)
    ? photosRaw.items
    : [];

  const handleFilePick = () => fileInputRef.current?.click();

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Dosya çok büyük. Maksimum 5MB yükleyebilirsiniz.');
      return;
    }
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      toast.error('Sadece JPG veya PNG yükleyebilirsiniz.');
      return;
    }
    setPhotoFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setPhotoPreview(ev.target.result);
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const removePhoto = () => {
    setPhotoFile(null);
    setPhotoPreview(null);
  };

  const reviewMutation = useMutation({
    mutationFn: (payload) => placeService.addReview(id, payload),
  });
  const photoMutation = useMutation({
    mutationFn: (formData) => placeService.uploadPhoto(formData),
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    const hasComment = comment.trim().length > 0;
    const hasPhoto = !!photoFile;

    if (!hasComment && !hasPhoto) {
      toast.error('Yorum veya fotoğraf eklemelisiniz.');
      return;
    }

    let photoUploaded = false;
    let reviewSubmitted = false;
    let anyError = null;

    try {
      if (hasPhoto) {
        const formData = new FormData();
        formData.append('place_id', id);
        formData.append('file', photoFile);
        try {
          await photoMutation.mutateAsync(formData);
          photoUploaded = true;
        } catch (err) {
          const status = err.response?.status;
          if (status === 413) anyError = 'Fotoğraf 5MB sınırını aştı.';
          else if (status === 415) anyError = 'Geçersiz fotoğraf formatı.';
          else anyError = 'Fotoğraf yüklenemedi.';
          throw err;
        }
      }

      if (hasComment) {
        const reviewPayload = {
          rating,
          body: comment.trim(),
          visited_at: new Date().toISOString().split('T')[0],
        };
        try {
          await reviewMutation.mutateAsync(reviewPayload);
          reviewSubmitted = true;
        } catch (err) {
          const detail = err.response?.data?.detail;
          if (err.response?.status === 409) {
            anyError = detail || 'Bu mekana zaten yorum yapmışsınız.';
          } else {
            anyError = detail || 'Yorum eklenemedi.';
          }
          throw err;
        }
      }
    } catch {
      // Aşağıda tek noktadan toast bas
    }

    if (photoUploaded || reviewSubmitted) {
      const parts = [];
      if (photoUploaded) parts.push('fotoğraf');
      if (reviewSubmitted) parts.push('yorum');
      toast.success(`${parts.join(' ve ')} eklendi!`);
      setComment('');
      setRating(5);
      removePhoto();
      queryClient.invalidateQueries({ queryKey: ['placeReviews', id] });
      queryClient.invalidateQueries({ queryKey: ['placePhotos', id] });
    }

    if (anyError && !photoUploaded && !reviewSubmitted) {
      toast.error(anyError);
    }
  };

  const isSubmitting = reviewMutation.isPending || photoMutation.isPending;

  return (
    <div className="min-h-screen bg-stone-100 p-6 md:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Üst Bilgi Kartı */}
        <div className="bg-white rounded-organic shadow-card overflow-hidden border border-stone-200">
          {place.kapak_foto_url && (
            <div className="h-56 md:h-72 bg-stone-200 overflow-hidden">
              <img src={place.kapak_foto_url} alt={placeName} className="w-full h-full object-cover" />
            </div>
          )}
          <div className="p-8">
            <Link
              to="/kesfet"
              className="inline-flex items-center gap-2 text-stone-500 hover:text-sienna mb-6 transition-colors font-ui"
            >
              <ArrowLeft size={18} /> Keşfet'e Dön
            </Link>

            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span
                className="text-[10px] font-ui px-2.5 py-1 rounded-badge uppercase tracking-wider text-white whitespace-nowrap"
                style={{ backgroundColor: categoryConfig.color }}
              >
                {categoryConfig.label}
              </span>
              {place.unesco && (
                <span className="text-[10px] font-ui bg-turquoise/15 text-turquoise px-2.5 py-1 rounded-badge whitespace-nowrap">
                  UNESCO Mirası
                </span>
              )}
              {aggregate?.average_rating != null && (
                <span className="inline-flex items-center gap-1 text-[12px] font-ui bg-amber/15 text-amber-700 px-2.5 py-1 rounded-badge whitespace-nowrap">
                  <Star size={12} fill="currentColor" />
                  {Number(aggregate.average_rating).toFixed(1)} ({aggregate.total})
                </span>
              )}
            </div>

            <h1 className="font-display text-3xl md:text-4xl text-sienna mb-4 leading-tight break-words">
              {placeName}
            </h1>

            <div className="flex items-center gap-2 text-stone-600 font-ui bg-stone-50 px-3 py-1.5 rounded-full border border-stone-100 w-max max-w-full mb-6">
              <MapPin size={16} className="text-turquoise shrink-0" />
              <span className="truncate">{place.sehir || place.city || 'İzmir'}</span>
            </div>

            <p className="font-body text-stone-700 leading-relaxed text-base md:text-lg whitespace-pre-line">
              {placeDesc}
            </p>
          </div>
        </div>

        {/* Fotoğraf Galerisi */}
        {(isPhotosLoading || photos.length > 0) && (
          <div className="bg-white rounded-organic shadow-card border border-stone-200 p-6 md:p-8">
            <h2 className="font-display text-xl text-stone-800 mb-4 flex items-center gap-2">
              <Camera className="text-sienna" /> Ziyaretçi Fotoğrafları
              {photos.length > 0 && (
                <span className="font-ui text-sm text-stone-500">({photos.length})</span>
              )}
            </h2>
            {isPhotosLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {photos.map((p) => (
                  <a
                    key={p.id}
                    href={p.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block bg-stone-100 rounded-lg overflow-hidden aspect-square hover:opacity-90 transition-opacity"
                  >
                    <img src={p.thumb_url || p.url} alt="Mekan" className="w-full h-full object-cover" />
                  </a>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Yorumlar + Birleşik Yorum/Foto Formu */}
        <div className="bg-white rounded-organic shadow-card border border-stone-200 p-6 md:p-8">
          <h2 className="font-display text-2xl text-stone-800 mb-6 flex items-center gap-2">
            <MessageSquare className="text-sienna" /> Ziyaretçi Yorumları
          </h2>

          <form
            onSubmit={handleSubmit}
            className="mb-10 bg-sand/30 p-5 md:p-6 rounded-card border border-stone-100"
          >
            <h3 className="font-ui font-semibold text-stone-800 mb-4">Deneyiminizi Paylaşın</h3>

            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <span className="font-ui text-sm text-stone-600 mr-1">Puanınız:</span>
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => setRating(star)}
                  aria-label={`${star} yıldız`}
                  className={`transition-colors ${
                    star <= rating ? 'text-amber' : 'text-stone-300 hover:text-amber/50'
                  }`}
                >
                  <Star size={24} fill={star <= rating ? 'currentColor' : 'none'} />
                </button>
              ))}
              <span className="ml-1 font-ui text-xs text-stone-500">(yorum yaparken zorunlu)</span>
            </div>

            {/* Fotoğraf önizleme — yorumun ÜSTÜNDE gözükür */}
            {photoPreview && (
              <div className="relative mb-4 inline-block max-w-full">
                <img
                  src={photoPreview}
                  alt="Yüklenecek fotoğraf"
                  className="max-h-56 rounded-card border border-stone-200 shadow-card"
                />
                <button
                  type="button"
                  onClick={removePhoto}
                  className="absolute top-2 right-2 bg-white/90 hover:bg-white text-rose-rug rounded-full p-1 shadow-card transition-colors"
                  aria-label="Fotoğrafı kaldır"
                >
                  <X size={16} />
                </button>
              </div>
            )}

            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Bu mekan hakkında ne düşünüyorsunuz? (sadece fotoğraf eklemek de yeterlidir)"
              className="w-full bg-white border border-stone-200 rounded-card p-4 font-ui focus:outline-none focus:ring-2 focus:ring-amber/30 focus:border-amber resize-none min-h-[110px] mb-3"
            />

            <input
              ref={fileInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,image/jpeg,image/png"
              className="hidden"
              onChange={handleFileChange}
            />

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleFilePick}
                className="inline-flex items-center gap-2 bg-white border border-stone-200 text-stone-700 px-4 py-2.5 rounded-badge font-ui text-sm font-medium hover:border-amber hover:text-sienna transition-all"
                aria-label="Fotoğraf ekle"
              >
                <ImagePlus size={18} />
                {photoFile ? 'Fotoğrafı değiştir' : 'Fotoğraf ekle'}
              </button>

              <button
                type="submit"
                disabled={isSubmitting}
                className="ml-auto bg-sienna text-white px-6 py-2.5 rounded-badge font-ui font-semibold hover:bg-amber transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send size={18} />}
                Gönder
              </button>
            </div>
            <p className="font-ui text-xs text-stone-500 mt-3">
              Yorum, fotoğraf veya her ikisini birden ekleyebilirsin. JPG/PNG, en fazla 5MB.
            </p>
          </form>

          {isReviewsLoading ? (
            <div className="flex justify-center p-6">
              <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
            </div>
          ) : reviews.length === 0 ? (
            <p className="text-center font-ui text-stone-500 italic py-6">İlk yorumu yapan siz olun!</p>
          ) : (
            <div className="space-y-5">
              {reviews.map((review, idx) => {
                const userName = review?.author?.username || review?.user?.username || 'Gezgin';
                const userInitial = userName ? userName.charAt(0).toUpperCase() : 'G';
                const reviewText = String(review?.body || review?.comment || review?.text || '');
                const stars = Number(review?.rating) || 5;

                return (
                  <div key={review?.id || idx} className="border-b border-stone-100 pb-5 last:border-0">
                    <div className="flex justify-between items-start mb-2 gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-8 h-8 rounded-full bg-turquoise/20 text-turquoise flex items-center justify-center font-bold font-ui text-sm uppercase shrink-0">
                          {userInitial}
                        </div>
                        <span className="font-ui font-semibold text-stone-700 truncate">{userName}</span>
                      </div>
                      <div className="flex text-amber shrink-0">
                        {[...Array(5)].map((_, i) => (
                          <Star
                            key={i}
                            size={14}
                            fill={i < stars ? 'currentColor' : 'none'}
                            className={i >= stars ? 'text-stone-200' : ''}
                          />
                        ))}
                      </div>
                    </div>
                    {reviewText && (
                      <p className="font-body text-stone-700 text-sm md:text-[15px] leading-relaxed ml-10">
                        {reviewText}
                      </p>
                    )}
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
