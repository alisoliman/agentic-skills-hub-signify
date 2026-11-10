targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment.')
param environmentName string

@minLength(1)
@description('Primary Azure location for the resource group.')
param location string

@description('Optional resource group name. Defaults to rg-<environmentName>.')
param resourceGroupName string = ''

var resourceToken = toLower(uniqueString(environmentName, location))
// Static Web App names are limited to 40 characters: long environment names are shortened.
var webName = replace('stapp-${take(environmentName, 20)}-${resourceToken}', '--', '-')
var tags = {
  'azd-env-name': environmentName
  'azd-template': 'agentic-skills-hub'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : 'rg-${environmentName}'
  location: location
  tags: tags
}

module web './web.bicep' = {
  name: 'web'
  scope: rg
  params: {
    name: webName
    location: location
    tags: tags
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output SERVICE_WEB_NAME string = web.outputs.name
output SERVICE_WEB_URI string = web.outputs.uri
