// Kanonik kategori → görsel etiket + renk eşlemesi.
// Backend `places.kategori` taksonomisiyle (etl/normalize/category_taxonomy.py)
// uyumlu tutulur.
export const CATEGORY_CONFIG = {
  MUSEUM:                 { label: 'Müze',           color: '#2A9D8F' },
  ARCHAEOLOGICAL_SITE:    { label: 'Arkeolojik Alan',color: '#D4883A' },
  ANCIENT_CITY:           { label: 'Antik Kent',     color: '#B8650D' },
  MOSQUE:                 { label: 'Cami',           color: '#264653' },
  CHURCH:                 { label: 'Kilise',         color: '#7B5E57' },
  SYNAGOGUE:              { label: 'Sinagog',        color: '#5E548E' },
  PALACE:                 { label: 'Saray',          color: '#A0522D' },
  CASTLE:                 { label: 'Kale',           color: '#7F2A2A' },
  FORT:                   { label: 'Hisar',          color: '#7F2A2A' },
  TOWER:                  { label: 'Kule',           color: '#8A3B3B' },
  MONUMENT:               { label: 'Anıt',           color: '#6B5B4E' },
  FOUNTAIN:               { label: 'Çeşme',          color: '#3A8FB7' },
  AQUEDUCT:               { label: 'Su Kemeri',      color: '#3A8FB7' },
  BATH:                   { label: 'Hamam',          color: '#9C6B98' },
  CARAVANSERAI:           { label: 'Kervansaray',    color: '#8B6F47' },
  THEATRE:                { label: 'Tiyatro',        color: '#B95A4D' },
  AGORA:                  { label: 'Agora',          color: '#C28A2F' },
  LIBRARY:                { label: 'Kütüphane',      color: '#4A7C59' },
  RUINS:                  { label: 'Ören Yeri',      color: '#8B7355' },
  TOMB:                   { label: 'Türbe',          color: '#5C4A3D' },
  HISTORIC:               { label: 'Tarihi Alan',    color: '#6B5B4E' },
  HISTORIC_SITE:          { label: 'Tarihi Alan',    color: '#6B5B4E' },
  HISTORIC_DISTRICT:      { label: 'Tarihi Mahalle', color: '#7A6754' },
  RELIGIOUS_SITE:         { label: 'İbadethane',     color: '#5E548E' },
  ANCIENT_ARTWORK:        { label: 'Antik Eser',     color: '#A47148' },
  ARCHAEOLOGICAL_ARTIFACT:{ label: 'Arkeolojik Eser',color: '#A47148' },
  DEFAULT:                { label: 'Kültürel Miras', color: '#9E8E7E' },
};

export const getCategoryConfig = (code) => {
  if (!code) return CATEGORY_CONFIG.DEFAULT;
  const upperCode = String(code).toUpperCase();
  return CATEGORY_CONFIG[upperCode] || CATEGORY_CONFIG.DEFAULT;
};
