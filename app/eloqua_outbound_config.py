from dea.bulk.eml import eml

fields = {
    "id": eml.Contact.Id,
    "email": eml.Contact.Field("C_EmailAddress"),
    "firstName": eml.Contact.Field("C_FirstName"),
    "lastName": eml.Contact.Field("C_LastName"),
    "company": eml.Contact.Field("C_Company") or None
}
