# HIT 2 - Cloud Bursting con Terraform

Básicamente lo que hicimos acá fue extender el HIT1 para que los workers puedan correr en la nube (GCP) en vez de solo localmente. La idea del cloud bursting es: cuando la cola de RabbitMQ se llena de laburo, levantamos VMs en Google Cloud, ellas procesan los chunks del Sobel, y cuando terminamos las destruimos para no gastar guita al pedo.

La parte linda es que Terraform se encarga de todo el aprovisionamiento automáticamente, nosotros solo corremos un Python script y listo.

## Cómo ejecutar esto (para que funcione en la pc de un profe)

### Prerequisitos

- Tener una cuenta de GCP con un proyecto creado y facturación habilitada (sí, hay que poner tarjeta, pero con las VMs e2-micro el costo es mínimo si las destruís rápido)
- Tener instalado:
  - [Terraform](https://developer.hashicorp.com/terraform/install) (>= 1.3)
  - [Ngrok](https://ngrok.com/download) (la version gratuita alcanza)
  - [Python 3](https://www.python.org/downloads/)
  - Docker (para correr RabbitMQ y los workers locales del HIT1)
- Tener las credenciales de GPC configuradas. La forma mas facil es:
  1. Ir a GCP Console > IAM > Cuentas de servicio
  2. Crear una cuenta de servicio con rol "Editor"
  3. Generar una key JSON y descargarla
  4. Setear la variable de entorno:
     ```powershell
     $env:GOOGLE_APPLICATION_CREDENTIALS = "ruta\a\tu-key.json"
     ```

### Paso a paso

**1. RabbitMQ local**

Primero necesitamos que RabbitMQ esté corriendo en nuestra máquina para que los workers se conecten:

```powershell
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

**2. Levantar el túnel con Ngrok**

RabbitMQ corre local en el puerto 5672. Las VMs de GCP no pueden llegar a `localhost` de nuestra compu, entonces usamos Ngrok para exponer ese puerto con una URL pública:

```powershell
ngrok tcp 5672
```

Esto te va a mostrar una URL tipo `0.tcp.ngrok.io:12345`. La URL completa incluyendo el puerto es lo que vamos a necesitar en el próximo paso.

**3. Setear variables de entorno**

El orquestador necesita dos variables para funcionar (si no las setea, tira error y no arranca):

```powershell
$env:TF_VAR_project_id = "el-id-de-tu-proyecto-gcp"
$env:TF_VAR_rabbitmq_host = "0.tcp.ngrok.io:12345"   # la URL que te dio ngrok
```

**4. Correr el orquestador**

Pararse en la carpeta `tp3/HIT2/` y ejecutar:

```powershell
python orquestador.py
```

Esto hace:
- `terraform init` para descargar los providers de GCP
- `terraform apply` que crea las VMs en GCP (por defecto 2 VMs e2-micro)
- Espera 60 segundos para que las VMs arranquen, instalen Docker y bajen la imagen del worker
- Te queda esperando que apretés ENTER

**5. En otra terminal, correr splitter y joiner del HIT1**

Mientras el orquestador está esperando, abrí otra terminal y corre:

```
# Terminal 1: el joiner
python tp3/HIT1/parte_2_distribuido/joiner.py

# Terminal 2: el splitter
python tp3/HIT1/parte_2_distribuido/splitter.py
```

Los workers de GCP van a agarrar los chunks de la cola y procesarlos.

**6. Destruir todo**

Cuando termines de procesar las imágenes, volvé a la terminal del orquestador y apretá ENTER. Terraform va a ejecutar `destroy` y apagar las VMs para no gastar más créditos.