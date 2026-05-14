"""MultiLanguage - Additional methods."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.multi_language")


class MultiLanguageExtraMixin:
    """Additional methods mixin."""

    def _generate_go(self, entities: List[Dict], project_name: str,
                      description: str) -> Dict[str, str]:
        """Generate Go Gin project."""
        files = {}
        mod_name = project_name.lower().replace("-", "_")

        # go.mod
        files["go.mod"] = f'''module {mod_name}

go 1.21

require (
\tgithub.com/gin-gonic/gin v1.9.1
\tgorm.io/gorm v1.25.0
\tgorm.io/driver/sqlite v1.5.0
)
'''

        # Models
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "go")
            files[f"models/{name.lower()}.go"] = self._go_model(name, fields, mod_name)
            files[f"handlers/{name.lower()}.go"] = self._go_handler(name, mod_name)

        # main.go
        files["main.go"] = self._go_main(project_name, entities, mod_name)

        # Dockerfile
        files["Dockerfile"] = self._go_dockerfile(mod_name)

        return files

    def _go_model(self, name: str, fields: List[Dict], mod_name: str) -> str:
        field_defs = "\n".join(
            f"\t{f['name'].capitalize()} {f['type']} `json:\"{f['name']}\" gorm:\"column:{f['name']}\"`"
            for f in fields
        )
        return f'''package models

import "time"

// {name} model
type {name} struct {{
{field_defs}
}}

// TableName overrides the table name
func ({name}) TableName() string {{
\treturn "{name.lower()}s"
}}
'''

    def _go_handler(self, name: str, mod_name: str) -> str:
        return f'''package handlers

import (
\t"net/http"
\t"strconv"
\t"{mod_name}/models"
\t"github.com/gin-gonic/gin"
\t"gorm.io/gorm"
)

type {name}Handler struct {{
\tDB *gorm.DB
}}

func New{name}Handler(db *gorm.DB) *{name}Handler {{
\treturn &{name}Handler{{DB: db}}
}}

func (h *{name}Handler) Create(c *gin.Context) {{
\tvar item models.{name}
\tif err := c.ShouldBindJSON(&item); err != nil {{
\t\tc.JSON(http.StatusBadRequest, gin.H{{"error": err.Error()}})
\t\treturn
\t}}
\th.DB.Create(&item)
\tc.JSON(http.StatusCreated, item)
}}

func (h *{name}Handler) GetByID(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\tvar item models.{name}
\tif err := h.DB.First(&item, id).Error; err != nil {{
\t\tc.JSON(http.StatusNotFound, gin.H{{"error": "{name} not found"}})
\t\treturn
\t}}
\tc.JSON(http.StatusOK, item)
}}

func (h *{name}Handler) List(c *gin.Context) {{
\tlimit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
\toffset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
\tvar items []models.{name}
\th.DB.Limit(limit).Offset(offset).Find(&items)
\tc.JSON(http.StatusOK, items)
}}

func (h *{name}Handler) Update(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\tvar item models.{name}
\tif err := h.DB.First(&item, id).Error; err != nil {{
\t\tc.JSON(http.StatusNotFound, gin.H{{"error": "{name} not found"}})
\t\treturn
\t}}
\tc.ShouldBindJSON(&item)
\th.DB.Save(&item)
\tc.JSON(http.StatusOK, item)
}}

func (h *{name}Handler) Delete(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\th.DB.Delete(&models.{name}{{}}, id)
\tc.JSON(http.StatusOK, gin.H{{"success": true}})
}}
'''

    def _go_main(self, project_name: str, entities: List[Dict], mod_name: str) -> str:
        imports = [f'\t"{mod_name}/handlers"' for _ in entities]
        routes = []
        for e in entities:
            name = e.get("name", "Item")
            routes.append(f'\t{name.lower()}Handler := handlers.New{name}Handler(db)')
            routes.append(f'\tv1.GET("/{name.lower()}s", {name.lower()}Handler.List)')
            routes.append(f'\tv1.GET("/{name.lower()}s/:id", {name.lower()}Handler.GetByID)')
            routes.append(f'\tv1.POST("/{name.lower()}s", {name.lower()}Handler.Create)')
            routes.append(f'\tv1.PUT("/{name.lower()}s/:id", {name.lower()}Handler.Update)')
            routes.append(f'\tv1.DELETE("/{name.lower()}s/:id", {name.lower()}Handler.Delete)')

        return f'''package main

import (
\t"{mod_name}/models"
\t"github.com/gin-gonic/gin"
\t"gorm.io/driver/sqlite"
\t"gorm.io/gorm"
{chr(10).join(set(imports))}
)

func main() {{
\tdb, err := gorm.Open(sqlite.Open("data.sqlite"), &gorm.Config{{}})
\tif err != nil {{
\t\tpanic("failed to connect database")
\t}}
{chr(10).join([f"\tdb.AutoMigrate(&models.{e['name']}{{}})" for e in entities])}

\tr := gin.Default()
\tv1 := r.Group("/v1")
\t{{
{chr(10).join(routes)}
\t}}

\tr.GET("/health", func(c *gin.Context) {{
\t\tc.JSON(200, gin.H{{"status": "ok", "service": "{project_name}"}})
\t}})

\tr.Run(":3000")
}}
'''

    def _go_dockerfile(self, mod_name: str) -> str:
        return f'''FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -o /app/server .

FROM alpine:3.18
RUN apk add --no-cache gcc musl-dev
COPY --from=builder /app/server /app/server
EXPOSE 3000
CMD ["/app/server"]
'''

    # ================================================================
    #  KOTLIN (Spring Boot + JPA)
    # ================================================================

    def _generate_kotlin(self, entities: List[Dict], project_name: str,
                          description: str) -> Dict[str, str]:
        """Generate Kotlin Spring Boot project."""
        files = {}
        pkg = project_name.lower().replace("-", ".")

        # build.gradle.kts
        files["build.gradle.kts"] = self._kt_build(project_name)

        # Application main
        files["src/main/kotlin/Application.kt"] = self._kt_main(project_name, pkg)

        # Entity + Repository + Service + Controller for each entity
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "kotlin")
            base = f"src/main/kotlin/{pkg.replace('.', '/')}"
            files[f"{base}/models/{name}.kt"] = self._kt_model(name, fields, pkg)
            files[f"{base}/repositories/{name}Repository.kt"] = self._kt_repository(name, pkg)
            files[f"{base}/services/{name}Service.kt"] = self._kt_service(name, pkg)
            files[f"{base}/controllers/{name}Controller.kt"] = self._kt_controller(name, pkg)

        return files

    def _kt_build(self, name: str) -> str:
        return f'''plugins {{
\tkotlin("jvm") version "1.9.20"
\tkotlin("plugin.spring") version "1.9.20"
\tkotlin("plugin.jpa") version "1.9.20"
\tid("org.springframework.boot") version "3.2.0"
\tid("io.spring.dependency-management") version "1.1.4"
}}

group = "{name.lower()}"
version = "1.0.0"

dependencies {{
\timplementation("org.springframework.boot:spring-boot-starter-web")
\timplementation("org.springframework.boot:spring-boot-starter-data-jpa")
\timplementation("org.springframework.boot:spring-boot-starter-validation")
\timplementation("com.fasterxml.jackson.module:jackson-module-kotlin")
\timplementation("org.jetbrains.kotlin:kotlin-reflect")
\truntimeOnly("com.h2database:h2")
\ttestImplementation("org.springframework.boot:spring-boot-starter-test")
}}
'''

    def _kt_main(self, name: str, pkg: str) -> str:
        return f'''package {pkg}

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class Application

fun main(args: Array<String>) {{
\trunApplication<Application>(*args)
}}
'''

    def _kt_model(self, name: str, fields: List[Dict], pkg: str) -> str:
        props = "\n".join(
            f'\tval {f["name"]}: {f["type"]}' + ('? = null' if f["name"] != "id" else ' = null')
            for f in fields
        )
        return f'''package {pkg}.models

import jakarta.persistence.*

@Entity
@Table(name = "{name.lower()}s")
data class {name}(
{props}
)
'''

    def _kt_repository(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.repositories

import {pkg}.models.{name}
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

@Repository
interface {name}Repository : JpaRepository<{name}, Long>
'''

    def _kt_service(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.services

import {pkg}.models.{name}
import {pkg}.repositories.{name}Repository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service

@Service
class {name}Service(private val repository: {name}Repository) {{

\tfun findAll(limit: Int = 50, offset: Int = 0): List<{name}> =
\t\trepository.findAll(PageRequest.of(offset / limit, limit)).content

\tfun findById(id: Long): {name}? = repository.findById(id).orElse(null)

\tfun create(item: {name}): {name} = repository.save(item)

\tfun update(id: Long, item: {name}): {name}? {{
\t\treturn if (repository.existsById(id)) repository.save(item) else null
\t}}

\tfun delete(id: Long): Boolean {{
\t\treturn if (repository.existsById(id)) {{ repository.deleteById(id); true }} else false
\t}}
}}
'''

    def _kt_controller(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.controllers

import {pkg}.models.{name}
import {pkg}.services.{name}Service
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/v1/{name.lower()}s")
class {name}Controller(private val service: {name}Service) {{

\t@GetMapping
\tfun list(@RequestParam(defaultValue = "50") limit: Int,
\t          @RequestParam(defaultValue = "0") offset: Int): List<{name}> =
\t\tservice.findAll(limit, offset)

\t@GetMapping("/{{id}}")
\tfun getById(@PathVariable id: Long): ResponseEntity<{name}> =
\t\tservice.findById(id)?.let {{ ResponseEntity.ok(it) }}
\t\t\t?: ResponseEntity.notFound().build()

\t@PostMapping
\tfun create(@RequestBody item: {name}): ResponseEntity<{name}> =
\t\tResponseEntity.status(HttpStatus.CREATED).body(service.create(item))

\t@PutMapping("/{{id}}")
\tfun update(@PathVariable id: Long, @RequestBody item: {name}): ResponseEntity<{name}> =
\t\tservice.update(id, item)?.let {{ ResponseEntity.ok(it) }}
\t\t\t?: ResponseEntity.notFound().build()

\t@DeleteMapping("/{{id}}")
\tfun delete(@PathVariable id: Long): ResponseEntity<Map<String, Boolean>> =
\t\tif (service.delete(id)) ResponseEntity.ok(mapOf("success" to true))
\t\telse ResponseEntity.notFound().build()
}}
'''
