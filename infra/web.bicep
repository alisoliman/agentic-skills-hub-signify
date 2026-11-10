@description('Static Web App resource name.')
param name string

@description('Azure location for the Static Web App.')
param location string = resourceGroup().location

@description('Tags applied to the Static Web App.')
param tags object = {}

resource web 'Microsoft.Web/staticSites@2024-04-01' = {
  name: name
  location: location
  tags: union(tags, {
    'azd-service-name': 'web'
  })
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    provider: 'Custom'
  }
}

output name string = web.name
output uri string = 'https://${web.properties.defaultHostname}'

