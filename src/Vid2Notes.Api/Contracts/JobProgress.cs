namespace Vid2Notes.Api.Contracts;

public record JobProgress(Guid JobId, string Stage, int Percent);
