variable "project_id" {
  description = "ID del proyecto de GCP"
  type        = string
}

variable "region" {
  description = "Región de GCP"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zona de GCP"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "Tipo de máquina para los workers"
  type        = string
  default     = "e2-micro" # Usamos micro para no gastar mucho, aunque podría ser e2-medium
}

variable "worker_count" {
  description = "Cantidad de nodos worker a levantar (cloud bursting)"
  type        = number
  default     = 2
}

variable "rabbitmq_host" {
  description = "Dirección IP pública o dominio de Ngrok donde escucha RabbitMQ"
  type        = string
}

variable "worker_image" {
  description = "Nombre de la imagen Docker del worker de Sobel"
  type        = string
  default     = "tobiasavila142/sobel-worker:latest"
}
