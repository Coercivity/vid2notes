FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY src/Vid2Notes.Api/Vid2Notes.Api.csproj src/Vid2Notes.Api/
RUN dotnet restore src/Vid2Notes.Api/Vid2Notes.Api.csproj
COPY src/ src/
RUN dotnet publish src/Vid2Notes.Api/Vid2Notes.Api.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
EXPOSE 8080
ENTRYPOINT ["dotnet", "Vid2Notes.Api.dll"]
