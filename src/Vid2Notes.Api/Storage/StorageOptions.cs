namespace Vid2Notes.Api.Storage;

public class StorageOptions
{
    public const string SectionName = "Storage";

    public required string Endpoint { get; set; }
    public required string AccessKey { get; set; }
    public required string SecretKey { get; set; }
    public required string Bucket { get; set; }
}
