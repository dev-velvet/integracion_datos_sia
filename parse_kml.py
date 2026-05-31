import os
import sys
import re
import csv
import json
import requests
from xml.etree import ElementTree as ET

# Configurar salida estándar en UTF-8 para evitar errores con caracteres especiales en Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def clean_xml_namespaces(xml_string):
    """
    Elimina los namespaces XML para facilitar el parsing genérico de KML
    sin importar qué esquemas o prefijos utilice.
    """
    # Eliminar namespaces por defecto y con prefijo de las etiquetas de apertura
    xml_string = re.sub(r'\sxmlns="[^"]+"', '', xml_string)
    xml_string = re.sub(r'\sxmlns:\w+="[^"]+"', '', xml_string)
    # Eliminar prefijos de namespaces en las etiquetas (ej: gx:drawOrder -> drawOrder)
    xml_string = re.sub(r'<(\/?)\w+:(\w+)', r'<\1\2', xml_string)
    # Eliminar cualquier otro atributo que tenga prefijo de namespace (ej: gx:balloonVisibility)
    xml_string = re.sub(r'\s\w+:(\w+="[^"]+")', r' \1', xml_string)
    return xml_string


def load_kml(source):
    """
    Carga un archivo KML desde una ruta local o una URL.
    Retorna el árbol XML parseado y limpio de namespaces.
    """
    print(f"Cargando KML desde: {source}...")
    
    if source.startswith(('http://', 'https://')):
        # Cargar desde URL
        response = requests.get(source, timeout=20, verify=False)
        response.raise_for_status()
        content = response.content.decode('utf-8', errors='ignore')
    else:
        # Cargar desde archivo local
        if not os.path.exists(source):
            raise FileNotFoundError(f"El archivo local '{source}' no existe.")
        with open(source, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

    # Limpiar namespaces
    cleaned_content = clean_xml_namespaces(content)
    
    # Parsear XML
    return ET.fromstring(cleaned_content)


def extract_placemarks(root):
    """
    Extrae recursivamente la información de todos los Placemarks en el KML.
    """
    placemarks_data = []
    
    # Encontrar todos los elementos Placemark
    placemarks = root.findall('.//Placemark')
    print(f"Se encontraron {len(placemarks)} placemarks (puntos/geometrías).")
    
    for idx, pm in enumerate(placemarks, 1):
        name = pm.findtext('name', f"Elemento #{idx}").strip()
        description = pm.findtext('description', '').strip()
        
        # 1. Extraer coordenadas (Lon, Lat, Alt)
        lon, lat, alt = None, None, None
        coord_node = pm.find('.//coordinates')
        if coord_node is not None and coord_node.text:
            coords_str = coord_node.text.strip()
            # En KML las coordenadas pueden estar separadas por espacios si hay múltiples (ej. rutas/polígonos)
            # Para placemarks de puntos, normalmente hay una sola terna: lon,lat,alt
            first_coord = coords_str.split()[0] if coords_str else ""
            parts = first_coord.split(',')
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    if len(parts) >= 3:
                        alt = float(parts[2])
                except ValueError:
                    pass

        # 2. Extraer todos los datos de ExtendedData (SimpleData y Data)
        extended_fields = {}
        
        # Caso A: <SimpleData name="campo">valor</SimpleData>
        for simple_data in pm.findall('.//SimpleData'):
            field_name = simple_data.get('name')
            if field_name:
                extended_fields[field_name] = (simple_data.text or '').strip()
                
        # Caso B: <Data name="campo"><value>valor</value></Data>
        for data_node in pm.findall('.//Data'):
            field_name = data_node.get('name')
            val_node = data_node.find('value')
            if field_name and val_node is not None:
                extended_fields[field_name] = (val_node.text or '').strip()

        # Construir registro unificado
        record = {
            'nombre': name,
            'latitud': lat,
            'longitud': lon,
            'altitud': alt,
            'descripcion': description
        }
        # Agregar los campos extendidos al registro
        record.update(extended_fields)
        placemarks_data.append(record)
        
    return placemarks_data


def save_data(data, output_base_name, format_type='csv'):
    """
    Guarda los datos extraídos en formato CSV o JSON.
    """
    if not data:
        print("No hay datos para guardar.")
        return

    # Obtener todas las llaves posibles para los encabezados (de forma dinámica)
    headers = list(data[0].keys())
    for row in data:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    filename = f"{output_base_name}.{format_type}"
    
    if format_type.lower() == 'csv':
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Datos guardados correctamente en CSV: {os.path.abspath(filename)}")
        
    elif format_type.lower() == 'json':
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ Datos guardados correctamente en JSON: {os.path.abspath(filename)}")


def main():
    # Permitir pasar la ruta/URL como argumento o solicitarla si no se especifica
    if len(sys.argv) > 1:
        source = sys.argv[1]
    else:
        print("--- PARSER GENÉRICO DE KML ---")
        source = input("Introduce la ruta del archivo KML local o una URL: ").strip()
        # Eliminar comillas que a veces se agregan al arrastrar archivos a la consola
        source = source.strip('\'"')

    if not source:
        print("Error: Debes proporcionar un archivo KML o URL.")
        sys.exit(1)

    try:
        # Obtener el nombre base del archivo para el output
        if source.startswith(('http://', 'https://')):
            base_name = source.split('/')[-1].split('?')[0] or "datos_kml"
        else:
            base_name = os.path.splitext(os.path.basename(source))[0]
        
        # Eliminar caracteres no válidos para nombres de archivo
        base_name = re.sub(r'[\\/*?:"<>| ]', '_', base_name)

        # 1. Cargar y limpiar el XML del KML
        kml_root = load_kml(source)
        
        # 2. Extraer placemarks
        data = extract_placemarks(kml_root)
        
        if not data:
            print("No se pudieron extraer datos de placemarks del KML proporcionado.")
            sys.exit(0)

        # 3. Mostrar vista previa
        print(f"\n--- Vista previa de los primeros 5 registros de '{base_name}' ---")
        preview_cols = ['nombre', 'latitud', 'longitud']
        # Buscar hasta 3 campos extendidos adicionales comunes para mostrar en la consola
        all_keys = data[0].keys()
        ext_keys = [k for k in all_keys if k not in preview_cols and k != 'altitud' and k != 'descripcion']
        preview_cols.extend(ext_keys[:3])
        
        # Encabezado de tabla
        header_str = " | ".join(f"{col.upper():<25}" for col in preview_cols)
        print(header_str)
        print("-" * len(header_str))
        
        for item in data[:5]:
            row_str = " | ".join(f"{str(item.get(col, '')):<25}"[:25] for col in preview_cols)
            print(row_str)

        # 4. Guardar datos automáticamente en CSV y JSON
        print("\nExportando datos...")
        save_data(data, base_name, 'csv')
        save_data(data, base_name, 'json')
        
    except Exception as e:
        print(f"\n❌ Error al procesar el KML: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
