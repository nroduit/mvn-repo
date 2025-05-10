## Maven Repository ##

This is the Maven repository for third-party libraries not available in Maven Central. To use this repository maven add in your pom.xml:

``` xml
  <repositories>
    <repository>
      <snapshots>
        <enabled>false</enabled>
      </snapshots>
      <id>central</id>
      <name>Central Repository</name>
      <url>https://repo.maven.apache.org/maven2</url>
    </repository>
    <repository>
      <snapshots>
        <enabled>false</enabled>
      </snapshots>
      <id>mvn-repo-master</id>
      <url>https://raw.github.com/nroduit/mvn-repo/master/</url>
    </repository>
  </repositories>
```
