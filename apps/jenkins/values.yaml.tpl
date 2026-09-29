# Jenkins chart values for the Fortify lab (jenkins/jenkins chart).
# Rendered by apps/jenkins/common.sh (jenkins_render_values); ${...} values
# come from .env. Objects created by start.sh, not the chart:
#   Secret    jenkins-admin          admin user and password
#   ConfigMap fortifylab-root-ca     the lab root CA ($ROOTCA_CERT)
#   ConfigMap jenkins-agent-init     apps/jenkins/agent-init.sh
#   PVC       jenkins-home           controller data (kept by destroy unless confirmed)
#   PVC       jenkins-agent-tools    shared agent tools, including fcli

controller:
  image:
    tag: "${FORTIFY_JENKINS_IMAGE_TAG}"
  jenkinsUrl: "${JENKINS_URL}/"
  jenkinsUrlProtocol: https
  admin:
    createSecret: false
    existingSecret: jenkins-admin
    userKey: jenkins-admin-user
    passwordKey: jenkins-admin-password
  serviceType: ClusterIP
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: "2"
      memory: 3Gi
  # The controller trusts the lab CA plus the image's public CAs, so plugins
  # and webhooks can call https://*.<DOMAIN>.
  javaOpts: "-Djavax.net.ssl.trustStore=/fortifylab-trust/cacerts -Djavax.net.ssl.trustStorePassword=changeit"
  containerEnv:
    - name: SSL_CERT_FILE
      value: /fortifylab-trust/ca-bundle.crt
    - name: GIT_SSL_CAINFO
      value: /fortifylab-trust/ca-bundle.crt
  customInitContainers:
    - name: fortifylab-trust
      image: "docker.io/jenkins/jenkins:${FORTIFY_JENKINS_IMAGE_TAG}"
      imagePullPolicy: IfNotPresent
      command: ["bash", "/fortifylab-init/agent-init.sh"]
      env:
        - name: FORTIFY_JENKINS_FCLI_INSTALL
          value: none
      volumeMounts:
        - name: fortifylab-ca
          mountPath: /fortifylab-ca
          readOnly: true
        - name: fortifylab-init
          mountPath: /fortifylab-init
          readOnly: true
        - name: fortifylab-trust
          mountPath: /fortifylab-trust
    # The chart's init container copies plugins with `yes n | cp -i` under
    # `set -e`. coreutils 9.x makes a declined overwrite exit 1, so when the
    # pod restarts in place (node reboot) and its plugin-dir emptyDir still
    # holds plugins, init crash-loops. Empty it first; init refills it from
    # the plugin cache on every start.
    - name: fortifylab-plugin-dir-reset
      image: "docker.io/jenkins/jenkins:${FORTIFY_JENKINS_IMAGE_TAG}"
      imagePullPolicy: IfNotPresent
      command: ["sh", "-c", "rm -f /var/jenkins_plugins/*.jpi /var/jenkins_plugins/*.hpi"]
      volumeMounts:
        - name: plugin-dir
          mountPath: /var/jenkins_plugins
  ingress:
    enabled: true
    ingressClassName: public
    hostName: "${JENKINS}"
    path: /
    pathType: Prefix
    annotations:
      traefik.ingress.kubernetes.io/router.tls: "true"
      nginx.ingress.kubernetes.io/proxy-body-size: 100m
    tls:
      - secretName: tls
        hosts:
          - "${JENKINS}"

persistence:
  existingClaim: jenkins-home
  volumes:
    - name: fortifylab-ca
      configMap:
        name: fortifylab-root-ca
    - name: fortifylab-init
      configMap:
        name: jenkins-agent-init
    - name: fortifylab-trust
      emptyDir: {}
  mounts:
    - name: fortifylab-trust
      mountPath: /fortifylab-trust
      readOnly: true

agent:
  image:
    repository: jenkins/inbound-agent
    tag: "${FORTIFY_JENKINS_AGENT_IMAGE_TAG}"
  customJenkinsLabels:
    - fortifylab
  containerCap: ${JENKINS_AGENT_MAX}
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: "1"
      memory: 2Gi
  # Merged into every agent pod: the init container builds the trust bundle
  # and installs fcli and Maven; the jnlp container gets the bundle, the tools volume,
  # and env vars so Java, git, curl, Python, Node, and fcli trust the lab.
  yamlMergeStrategy: merge
  yamlTemplate: |-
    apiVersion: v1
    kind: Pod
    spec:
      securityContext:
        fsGroup: 1000
      initContainers:
        - name: fortifylab-init
          image: "jenkins/inbound-agent:${FORTIFY_JENKINS_AGENT_IMAGE_TAG}"
          imagePullPolicy: IfNotPresent
          command: ["bash", "/fortifylab-init/agent-init.sh"]
          env:
            - name: FORTIFY_JENKINS_FCLI_INSTALL
              value: "${FORTIFY_JENKINS_FCLI_INSTALL}"
            - name: FORTIFY_JENKINS_FCLI_VERSION
              value: "${FORTIFY_JENKINS_FCLI_VERSION}"
            - name: FORTIFY_JENKINS_MAVEN_VERSION
              value: "${FORTIFY_JENKINS_MAVEN_VERSION}"
          volumeMounts:
            - name: fortifylab-ca
              mountPath: /fortifylab-ca
              readOnly: true
            - name: fortifylab-init
              mountPath: /fortifylab-init
              readOnly: true
            - name: fortifylab-trust
              mountPath: /fortifylab-trust
            - name: fortifylab-tools
              mountPath: /fortifylab-tools
      containers:
        - name: jnlp
          env:
            - name: PATH
              value: /fortifylab-tools/bin:/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
            - name: JAVA_TOOL_OPTIONS
              value: "-Djavax.net.ssl.trustStore=/fortifylab-trust/cacerts -Djavax.net.ssl.trustStorePassword=changeit"
            - name: SSL_CERT_FILE
              value: /fortifylab-trust/ca-bundle.crt
            - name: CURL_CA_BUNDLE
              value: /fortifylab-trust/ca-bundle.crt
            - name: GIT_SSL_CAINFO
              value: /fortifylab-trust/ca-bundle.crt
            - name: REQUESTS_CA_BUNDLE
              value: /fortifylab-trust/ca-bundle.crt
            - name: NODE_EXTRA_CA_CERTS
              value: /fortifylab-trust/rootCA.pem
            - name: FCLI_DATA_DIR
              value: /fortifylab-trust/fcli-data
            - name: FORTIFYLAB_JAVA_TRUSTSTORE
              value: /fortifylab-trust/cacerts
            - name: FORTIFYLAB_CA_FILE
              value: /fortifylab-ca/rootCA.pem
          volumeMounts:
            - name: fortifylab-ca
              mountPath: /fortifylab-ca
              readOnly: true
            - name: fortifylab-trust
              mountPath: /fortifylab-trust
            - name: fortifylab-tools
              mountPath: /fortifylab-tools
      volumes:
        - name: fortifylab-ca
          configMap:
            name: fortifylab-root-ca
        - name: fortifylab-init
          configMap:
            name: jenkins-agent-init
        - name: fortifylab-trust
          emptyDir: {}
        - name: fortifylab-tools
          persistentVolumeClaim:
            claimName: jenkins-agent-tools
