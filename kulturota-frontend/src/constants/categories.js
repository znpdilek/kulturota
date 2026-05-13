// src/constants/categories.js
export const CATEGORY_CONFIG = {
  MUSEUM:               { label: 'Müze',           color: '#2A9D8F' }, // Turkuaz
  ARCHAEOLOGICAL_SITE:  { label: 'Arkeolojik Alan',color: '#D4883A' }, // Amber
  MOSQUE:               { label: 'Cami',           color: '#264653' }, // Indigo Tile
  PALACE:               { label: 'Saray',          color: '#A0522D' }, // Sienna
  HISTORIC:             { label: 'Tarihi Alan',    color: '#6B5B4E' }, // Stone-600
  CHURCH:               { label: 'Kilise',         color: '#9E8E7E' }, // Stone-400
  DEFAULT:              { label: 'Kültürel Miras', color: '#9E8E7E' }
};

export const getCategoryConfig = (code) => {
  if (!code) return CATEGORY_CONFIG.DEFAULT;
  // Gelen veriyi (örn: CHURCH) büyük harfe çevirip eşleştiriyoruz
  const upperCode = String(code).toUpperCase();
  return CATEGORY_CONFIG[upperCode] || CATEGORY_CONFIG.DEFAULT;
};