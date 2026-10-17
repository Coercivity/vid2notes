using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Endpoints.Models;

public record ExtractRequest(CropDto? Crop, SheetLayout? Layout, double? StartSeconds, double? EndSeconds);
