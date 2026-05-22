import requests
from xml.etree import ElementTree as ET
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def get_pm25_siata():
    url = "https://www.siata.gov.co/kml/01_Redes/AMVARedAire/RedAireAMVA_PM25.kml"
    
    r = requests.get(url, timeout=15, verify=False)
    r.raise_for_status()
    
    content = re.sub(b'xmlns="[^"]+"', b'', r.content)
    kml = ET.fromstring(content)
    
    estaciones = []
    for placemark in kml.findall('.//Placemark'):
        nombre = placemark.findtext('name', '').strip()
        
        val = None
        fecha = "Sin fecha"
        
        extended_data = placemark.find('.//SchemaData')
        if extended_data is not None:
            for simple_data in extended_data.findall('SimpleData'):
                nombre_campo = simple_data.get('name')
                
                # Buscamos el valor de PM2.5 (ICA)
                if nombre_campo == 'ICA_PM25_Valor':
                    try:
                        val = float(simple_data.text)
                        if val < 0:
                            val = None
                    except:
                        val = None
                
                elif nombre_campo == 'fecha_ultima_actualizacion':
                    fecha = simple_data.text
        
        # Coordenadas
        coords = placemark.findtext('.//coordinates', '')
        lon, lat = None, None
        if coords:
            partes = coords.strip().split(',')
            if len(partes) >= 2:
                lon, lat = float(partes[0]), float(partes[1])
        
        estaciones.append({
            'nombre': nombre,
            'pm25':   val,
            'fecha':  fecha,
            'lat':    lat,
            'lon':    lon,
        })
    
    return estaciones

def categoria_ica(pm25):
    if pm25 is None: return 'Sin dato'
    if pm25 < 12:    return '🟢 Buena'
    if pm25 < 35:    return '🟡 Moderada'
    if pm25 < 55:    return '🟠 Dañina para grupos sensibles'
    if pm25 < 150:   return '🔴 Dañina'
    if pm25 < 250:   return '🟣 Muy dañina'
    return '⛔ Peligrosa'

if __name__ == '__main__':
    print("Cargando PM2.5 desde SIATA...\n")
    estaciones = get_pm25_siata()
    
    # Filtrar y ordenar
    con_dato = [e for e in estaciones if e['pm25'] is not None]
    con_dato.sort(key=lambda x: x['pm25'], reverse=True)
    sin_dato = [e for e in estaciones if e['pm25'] is None]
    
    # Imprimir tabla con columna de tiempo
    print(f"{'Estación':<35} {'PM2.5':>8}   {'Tiempo':<20} Categoría")
    print("-" * 85)
    for e in con_dato:
        hora = e['fecha'].split(' ')[1] if ' ' in e['fecha'] else e['fecha']
        
        print(f"{e['nombre']:<35} {e['pm25']:>6.1f} ICA  [{hora:<8}] {categoria_ica(e['pm25'])}")
    
    if sin_dato:
        print(f"\nEstaciones sin dato actual: {len(sin_dato)}")
    
    if con_dato:
        promedio = sum(e['pm25'] for e in con_dato) / len(con_dato)
        print(f"\n--- Resumen ---")
        print(f"Total estaciones con dato: {len(con_dato)}")
        print(f"Promedio actual: {promedio:.1f} ICA  {categoria_ica(promedio)}")
